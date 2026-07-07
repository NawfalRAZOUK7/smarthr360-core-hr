"""Skill-gap prediction engine (Étape 4).

Projects, per department and skill, the competency *supply* six months ahead
and compares it to the *demand* (declared future needs + employee targets) to
surface the skill gaps most at risk. Inputs come from earlier stages:

* current competency levels          -> hr.EmployeeSkill (aggregated as in Étape 3)
* declared future needs              -> hr.FutureCompetency
* workforce attrition / headcount    -> hr.EmployeeProfileHistory (SCD2, Étape 2)

The analytic core (``analyzer``) is pure-Python and unit-testable; the service
layer adds the ORM data access.
"""

DEFAULT_HORIZON_MONTHS = 6
