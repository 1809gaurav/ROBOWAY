from .models import Job, Robot


def assignment_order(jobs: list[Job]) -> list[Job]:
    return sorted((job for job in jobs if job.state == "Waiting"), key=lambda job: (job.created_tick, job.id))


def robot_priority(robot: Robot, jobs: dict[str, Job]) -> tuple[int, str, str]:
    job = jobs.get(robot.job_id or "")
    carrying = robot.carrying is not None
    return (0 if carrying else 1, job.id if job else "~", robot.id)
