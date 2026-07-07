"""Run the skill-gap prediction engine from the CLI.

    python manage.py predict_skill_gaps [--department ENG] [--horizon 6]
                                        [--no-persist] [--top 20]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from hr.prediction.skill_gap_service import SkillGapEngine


class Command(BaseCommand):
    help = "Forecast skill gaps per department/skill and rank them by risk."

    def add_arguments(self, parser):
        parser.add_argument("--department", default=None)
        parser.add_argument("--horizon", type=int, default=6)
        parser.add_argument("--no-persist", action="store_true")
        parser.add_argument("--top", type=int, default=20)

    def handle(self, *args, **opts):
        engine = SkillGapEngine(horizon_months=opts["horizon"])
        run_id, forecasts = engine.run(
            department_code=opts["department"], persist=not opts["no_persist"]
        )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"run {run_id}: {len(forecasts)} forecast(s), horizon {opts['horizon']}m"
            )
        )
        for f in forecasts[: opts["top"]]:
            style = (
                self.style.ERROR
                if f["severity"] == "HIGH"
                else self.style.WARNING
                if f["severity"] == "MEDIUM"
                else self.style.SUCCESS
            )
            self.stdout.write(
                style(
                    f"  [{f['severity']:6}] {f['department_code']}/{f['skill_code']:12} "
                    f"gap={f['gap']:.1f} risk={f['risk_score']:.0f} "
                    f"proj={f['projected_level']:.1f}->dem={f['demand_level']:.1f}"
                )
            )
