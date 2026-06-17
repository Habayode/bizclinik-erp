"""School Phase 4 — attendance and results (GL-free).

Marking attendance and recording results are pure operational records: the
summary tallies statuses, record_result computes total + letter grade, the
report card aggregates a term's subjects into an average — and NONE of these
calls create a JournalEntry (no GL impact whatsoever).
"""
from __future__ import annotations

from datetime import date

import pytest


def _setup(s):
    """Seed a session + class + one enrolled student; return (sess, cls, student)."""
    from bizclinik_erp.services import school, school_enrol
    sess = school.create_academic_session(s, session_code="2025/2026",
                                          make_current=True)
    cls = school.create_school_class(s, class_code="JSS1A",
                                     name="Junior Secondary 1A", form_level=1)
    st_ = school_enrol.enrol_student(s, first_name="Ada", last_name="Obi",
                                     class_id=cls.id, academic_session_id=sess.id)
    return sess, cls, st_


def _journal_count(s) -> int:
    from bizclinik_erp.models import JournalEntry
    from sqlalchemy import func, select
    return s.execute(select(func.count()).select_from(JournalEntry)).scalar_one()


def test_attendance_and_summary_counts(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school, school_enrol, school_ops
    from bizclinik_erp.models import AttendanceStatus
    with get_session() as s:
        sess, cls, ada = _setup(s)
        bode = school_enrol.enrol_student(s, first_name="Bode", last_name="Cole",
                                          class_id=cls.id,
                                          academic_session_id=sess.id)
        chi = school_enrol.enrol_student(s, first_name="Chi", last_name="Eze",
                                         class_id=cls.id,
                                         academic_session_id=sess.id)
        eze = school_enrol.enrol_student(s, first_name="Eze", last_name="Udo",
                                         class_id=cls.id,
                                         academic_session_id=sess.id)
        d = date(2026, 1, 12)
        before = _journal_count(s)
        school_ops.record_attendance(s, student_id=ada.id, class_id=cls.id,
                                     attendance_date=d,
                                     status=AttendanceStatus.PRESENT)
        # status accepts a plain string too
        school_ops.record_attendance(s, student_id=bode.id, class_id=cls.id,
                                     attendance_date=d, status="ABSENT")
        school_ops.record_attendance(s, student_id=chi.id, class_id=cls.id,
                                     attendance_date=d, status="LATE")
        school_ops.record_attendance(s, student_id=eze.id, class_id=cls.id,
                                     attendance_date=d, status="EXCUSED")
        summ = school_ops.attendance_summary(s, cls.id, d)
        assert summ == {"present": 1, "absent": 1, "late": 1, "excused": 1,
                        "total": 4}
        # another day is independent
        assert school_ops.attendance_summary(
            s, cls.id, date(2026, 1, 13))["total"] == 0
        # no GL impact
        assert _journal_count(s) == before


def test_record_result_computes_total_and_grade(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_ops
    with get_session() as s:
        sess, cls, ada = _setup(s)
        before = _journal_count(s)
        res = school_ops.record_result(
            s, student_id=ada.id, class_id=cls.id,
            academic_session_id=sess.id, subject="Mathematics",
            term_number=1, ca_score=30, exam_score=50)
        assert res.total == 80          # 30 + 50
        assert res.grade == "A"         # >= 70
        # no GL impact from recording a result
        assert _journal_count(s) == before


def test_grade_boundaries():
    from bizclinik_erp.services.school_ops import _grade
    assert _grade(70) == "A"
    assert _grade(69.99) == "B"
    assert _grade(60) == "B"
    assert _grade(50) == "C"
    assert _grade(45) == "D"
    assert _grade(40) == "E"
    assert _grade(39.99) == "F"
    assert _grade(0) == "F"


def test_report_card_aggregates(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_ops
    with get_session() as s:
        sess, cls, ada = _setup(s)
        before = _journal_count(s)
        school_ops.record_result(s, student_id=ada.id, class_id=cls.id,
                                 academic_session_id=sess.id, subject="Maths",
                                 term_number=1, ca_score=30, exam_score=50)  # 80
        school_ops.record_result(s, student_id=ada.id, class_id=cls.id,
                                 academic_session_id=sess.id, subject="English",
                                 term_number=1, ca_score=20, exam_score=40)  # 60
        # a different term should NOT leak into the term-1 card
        school_ops.record_result(s, student_id=ada.id, class_id=cls.id,
                                 academic_session_id=sess.id, subject="Maths",
                                 term_number=2, ca_score=10, exam_score=10)  # 20
        card = school_ops.report_card(s, ada.id, sess.id, term_number=1)
        assert card["student"] == "Ada Obi"
        assert len(card["results"]) == 2
        assert card["average"] == 70.0          # (80 + 60) / 2
        subjects = {r["subject"]: r["grade"] for r in card["results"]}
        assert subjects == {"Maths": "A", "English": "B"}
        # the whole module is GL-free
        assert _journal_count(s) == before


def test_invalid_inputs_rejected(fresh_db):
    from bizclinik_erp.db import get_session
    from bizclinik_erp.services import school_ops
    with get_session() as s:
        sess, cls, ada = _setup(s)
        with pytest.raises(ValueError, match="Student not found"):
            school_ops.record_attendance(s, student_id=999999, class_id=cls.id,
                                         attendance_date=date.today(),
                                         status="PRESENT")
        with pytest.raises(ValueError, match="Invalid attendance status"):
            school_ops.record_attendance(s, student_id=ada.id, class_id=cls.id,
                                         attendance_date=date.today(),
                                         status="HOLIDAY")
        with pytest.raises(ValueError, match="term_number must be"):
            school_ops.record_result(s, student_id=ada.id,
                                     academic_session_id=sess.id,
                                     subject="Maths", term_number=4,
                                     ca_score=10, exam_score=10)
        with pytest.raises(ValueError, match="Subject is required"):
            school_ops.record_result(s, student_id=ada.id,
                                     academic_session_id=sess.id,
                                     subject="  ", term_number=1)
