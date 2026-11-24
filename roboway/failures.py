from .models import Job, Robot


def fail_robot(robot: Robot, jobs: dict[str, Job], tick: int) -> tuple[str | None, str | None]:
    job = jobs.get(robot.job_id or "")
    if job is None or job.state in ("Delivered", "Blocked"):
        robot.status = "failed"
        robot.path.clear()
        return None, None
    carrying = job.state == "PickedUp" or robot.carrying is not None
    if carrying:
        job.state = "Stranded"
        job.owner = None
        job.stranded_pos = robot.pos
        job.original_drop_id = job.drop_id
        job.pickup_id = f"STRANDED:{job.id}"
        job.history.append("Stranded")
        robot.status = "failed"
        robot.job_id = None
        robot.carrying = None
        robot.path.clear()
        return job.id, "stranded"
    job.state = "Waiting"
    job.owner = None
    job.history.append("Waiting")
    robot.status = "failed"
    robot.job_id = None
    robot.carrying = None
    robot.path.clear()
    return job.id, "reassigned"
