from backend.services.job_sources import (
    fetch_remotive_jobs,
    fetch_lever_jobs,
    fetch_greenhouse_jobs
)

def safe_call(fn):
    try:
        return fn()
    except Exception as e:
        print("Job source failed:", e)
        return []

def get_all_jobs():
    jobs = []
    jobs += safe_call(lambda: fetch_remotive_jobs())
    jobs += safe_call(lambda: fetch_lever_jobs("swiggy"))
    jobs += safe_call(lambda: fetch_greenhouse_jobs("microsoft"))

    # # Remote jobs (safe default)
    # jobs += fetch_remotive_jobs()

    # # Add a few companies
    # jobs += fetch_lever_jobs("swiggy")
    # jobs += fetch_lever_jobs("razorpay")

    # jobs += fetch_greenhouse_jobs("microsoft")
    # jobs += fetch_greenhouse_jobs("deloitte")

    return jobs