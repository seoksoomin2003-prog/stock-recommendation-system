import os
import sys
import time
import logging
from datetime import datetime, timedelta

# Add root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.daily_job import run_daily_job
from utils.logger import setup_logger

logger = setup_logger("Scheduler")

def start_scheduler():
    logger.info("Initializing Daily Recommendation Scheduler...")
    
    target_hour = 8
    target_minute = 0
    
    logger.info(f"Schedule configured for Daily at {target_hour:02d}:{target_minute:02d} KST/Local Time")
    
    while True:
        now = datetime.now()
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        
        # If target time has already passed today, schedule for tomorrow
        if target <= now:
            target += timedelta(days=1)
            
        wait_seconds = (target - now).total_seconds()
        hours, remainder = divmod(wait_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        logger.info(f"Next run scheduled at: {target}")
        logger.info(f"Sleeping for {int(hours)}h {int(minutes)}m {int(seconds)}s...")
        
        try:
            # Sleep until target time
            time.sleep(wait_seconds)
            
            logger.info("Waking up! Executing Daily Job...")
            run_daily_job()
            logger.info("Daily Job execution complete. Resetting for tomorrow.")
            
        except KeyboardInterrupt:
            logger.info("Scheduler interrupted by user. Exiting...")
            break
        except Exception as e:
            logger.error(f"Scheduler encountered an unexpected error: {e}")
            logger.info("Sleeping 60 seconds before resuming schedule loop to avoid spam...")
            time.sleep(60)

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # P6-19: project-relative paths
    start_scheduler()
