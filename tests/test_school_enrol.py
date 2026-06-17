"""School Phase 1 — students and enrolment. Enrolling a student must create the
billing Customer AND the Student AND the append-only enrolment row; admission
numbers auto-increment and stay unique; withdrawal flips status and stamps the
open enrolment row."""
from __future__ import annotations

from datetime import date

import pytest


def _setup_class_and_session(s):
    from bizclinik_erp.services import school
    sess = school.create_academic_session(s, session_code="2025/2026",
                                           make_current=True)
    cls = school.create_school_class(s, class_code="JSS1A",
                                     name="Junior Secondary 1A", form_level=1)
    return sess, cls


def test_enrol_creates_customer_student_and_enrolment(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_enrol
    from bizclinik_erp.models import (Customer, Student, StudentEnrolment,
                                      StudentStatus)
    from sqlalchemy import select
    with get_session() as s:
        sess, cls = _setup_class_and_session(s)
        st_ = school_enrol.enrol_student(
            s, first_name="Ada", last_name="Obi", class_id=cls.id,
            academic_session_id=sess.id, guardian_name="Mr Obi",
            guardian_phone="08000000000", dob=date(2014, 5, 1), gender="Female")
        assert st_.admission_no == "STU-0001"
        assert st_.status == StudentStatus.ACTIVE
        assert st_.current_class_id == cls.id
        # Customer (billing identity) created with code == admission_no
        cust = s.get(Customer, st_.customer_id)
        assert cust is not None and cust.code == "STU-0001"
        assert cust.name == "Ada Obi"
        # exactly one Student and one enrolment row
        n_students = len(s.execute(select(Student)).scalars().all())
        enrols = s.execute(select(StudentEnrolment).where(
            StudentEnrolment.student_id == st_.id)).scalars().all()
        assert n_students == 1
        assert len(enrols) == 1
        assert enrols[0].academic_session_id == sess.id
        assert enrols[0].class_id == cls.id
        assert enrols[0].withdrawn_at is None


def test_admission_no_auto_increments_and_is_unique(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_enrol
    with get_session() as s:
        sess, cls = _setup_class_and_session(s)
        a = school_enrol.enrol_student(s, first_name="Ada", last_name="Obi",
                                       class_id=cls.id, academic_session_id=sess.id)
        b = school_enrol.enrol_student(s, first_name="Bode", last_name="Cole",
                                       class_id=cls.id, academic_session_id=sess.id)
        assert a.admission_no == "STU-0001"
        assert b.admission_no == "STU-0002"
        # an explicit admission_no that collides is rejected
        with pytest.raises(ValueError, match="already exists"):
            school_enrol.enrol_student(s, first_name="Chi", last_name="Eze",
                                       class_id=cls.id, academic_session_id=sess.id,
                                       admission_no="STU-0001")


def test_withdraw_flips_status_and_stamps_enrolment(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_enrol
    from bizclinik_erp.models import StudentEnrolment, StudentStatus
    from sqlalchemy import select
    with get_session() as s:
        sess, cls = _setup_class_and_session(s)
        st_ = school_enrol.enrol_student(s, first_name="Ada", last_name="Obi",
                                         class_id=cls.id, academic_session_id=sess.id)
        school_enrol.withdraw_student(s, st_.id)
        s.refresh(st_)
        assert st_.status == StudentStatus.WITHDRAWN
        assert st_.is_active is False
        assert st_.status_date == date.today()
        enrol = s.execute(select(StudentEnrolment).where(
            StudentEnrolment.student_id == st_.id)).scalars().one()
        assert enrol.withdrawn_at is not None
        assert enrol.enrolment_status == "WITHDRAWN"


def test_list_students_filters_by_class_and_status(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school, school_enrol
    with get_session() as s:
        sess, cls = _setup_class_and_session(s)
        cls2 = school.create_school_class(s, class_code="JSS2A", name="JSS2A")
        a = school_enrol.enrol_student(s, first_name="Ada", last_name="Obi",
                                       class_id=cls.id, academic_session_id=sess.id)
        school_enrol.enrol_student(s, first_name="Bode", last_name="Cole",
                                   class_id=cls2.id, academic_session_id=sess.id)
        assert len(school_enrol.list_students(s)) == 2
        assert len(school_enrol.list_students(s, class_id=cls.id)) == 1
        school_enrol.withdraw_student(s, a.id)
        assert len(school_enrol.list_students(s, status="ACTIVE")) == 1
        assert len(school_enrol.list_students(s, status="WITHDRAWN")) == 1


def test_promote_appends_enrolment_and_updates_current_class(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school, school_enrol
    from bizclinik_erp.models import StudentEnrolment
    from sqlalchemy import select
    with get_session() as s:
        sess, cls = _setup_class_and_session(s)
        sess2 = school.create_academic_session(s, session_code="2026/2027")
        cls2 = school.create_school_class(s, class_code="JSS2A", name="JSS2A")
        st_ = school_enrol.enrol_student(s, first_name="Ada", last_name="Obi",
                                         class_id=cls.id, academic_session_id=sess.id)
        school_enrol.promote_student(s, st_.id, new_class_id=cls2.id,
                                     academic_session_id=sess2.id)
        s.refresh(st_)
        assert st_.current_class_id == cls2.id
        enrols = s.execute(select(StudentEnrolment).where(
            StudentEnrolment.student_id == st_.id)).scalars().all()
        assert len(enrols) == 2


# --------------------------------------------------------------------------- #
# Bulk student import                                                         #
# --------------------------------------------------------------------------- #

def test_bulk_import_enrols_with_class_and_billing(fresh_db):
    import pandas as pd
    from sqlalchemy import select, func
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school, school_enrol
    from bizclinik_erp.models import Student, StudentEnrolment, Customer
    with get_session() as s:
        sess, cls = _setup_class_and_session(s)
        school.create_school_class(s, class_code="PRY3", name="Primary 3")
        df = pd.DataFrame([
            {"first_name": "Ada", "last_name": "Okeke",
             "class_code": cls.class_code, "guardian_phone": "08030001111"},
            {"first_name": "Emeka", "last_name": "Bello", "class_code": "PRY3",
             "admission_no": "OTA/2025/014"},
        ])
        res = school_enrol.import_students(s, df, academic_session_id=sess.id)
        assert res["created"] == 2 and res["skipped"] == 0 and not res["errors"]
        assert s.execute(select(func.count()).select_from(Student)).scalar_one() == 2
        assert s.execute(select(func.count()).select_from(StudentEnrolment)).scalar_one() == 2
        emeka = s.execute(select(Student).where(Student.last_name == "Bello")).scalar_one()
        assert emeka.admission_no == "OTA/2025/014"
        assert s.get(Customer, emeka.customer_id).code == "OTA/2025/014"   # billing record
        ada = s.execute(select(Student).where(Student.last_name == "Okeke")).scalar_one()
        assert ada.admission_no.startswith("STU-")     # auto-numbered


def test_bulk_import_skips_bad_class_and_missing_name(fresh_db):
    import pandas as pd
    from sqlalchemy import select, func
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_enrol
    from bizclinik_erp.models import Student
    with get_session() as s:
        sess, cls = _setup_class_and_session(s)
        df = pd.DataFrame([
            {"first_name": "Good", "last_name": "Kid", "class_code": cls.class_code},
            {"first_name": "No", "last_name": "Class", "class_code": "ZZZ"},
            {"first_name": "", "last_name": "NoName", "class_code": cls.class_code},
        ])
        res = school_enrol.import_students(s, df, academic_session_id=sess.id)
        assert res["created"] == 1 and res["skipped"] == 2 and len(res["errors"]) == 2
        assert s.execute(select(func.count()).select_from(Student)).scalar_one() == 1


def test_bulk_import_duplicate_admission_skipped(fresh_db):
    import pandas as pd
    from sqlalchemy import select, func
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_enrol
    from bizclinik_erp.models import Student
    with get_session() as s:
        sess, cls = _setup_class_and_session(s)
        df = pd.DataFrame([
            {"first_name": "A", "last_name": "One", "class_code": cls.class_code,
             "admission_no": "DUP-1"},
            {"first_name": "B", "last_name": "Two", "class_code": cls.class_code,
             "admission_no": "DUP-1"},
        ])
        res = school_enrol.import_students(s, df, academic_session_id=sess.id)
        assert res["created"] == 1 and res["skipped"] == 1
        assert s.execute(select(func.count()).select_from(Student)).scalar_one() == 1


def test_student_template_is_valid_xlsx():
    import io
    import pandas as pd
    from bizclinik_erp.services import school_enrol
    data = school_enrol.student_template_bytes()
    assert data[:2] == b"PK"
    xl = pd.ExcelFile(io.BytesIO(data))
    assert "Students" in xl.sheet_names and "Instructions" in xl.sheet_names
    cols = list(xl.parse("Students").columns)
    assert {"first_name", "last_name", "class_code", "admission_no"} <= set(cols)
