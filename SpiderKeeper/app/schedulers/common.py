import threading
import time

from SpiderKeeper.app import scheduler, app, agent, db
from SpiderKeeper.app.spider.model import Project, JobInstance, SpiderInstance


def sync_job_execution_status_job():
    '''
    sync job execution running status
    :return:
    '''
    for project in Project.query.all():
        app.logger.debug('[sync_job_execution_status][project:%s]' % project.id)
        threading.Thread(target=agent.sync_job_status, args=(project,)).start()


def sync_spiders():
    '''
    sync spiders
    :return:
    '''
    for project in Project.query.all():
        spider_instance_list = agent.get_spider_list(project)
        SpiderInstance.update_spider_instances(spider_instance_list)


def run_spider_job(job_instance):
    '''
    run spider by scheduler
    :param job_instance:
    :return:
    '''
    threading.Thread(target=agent.start_spider, args=(job_instance,)).start()
    app.logger.info('[run_spider_job][project:%s][spider_name:%s][job_instance_id:%s]' % (
        job_instance.project_id, job_instance.spider_name, job_instance.id))


def reload_runnable_spider_job_execution():
    '''
    add periodic job to scheduler
    :return:
    '''
    running_job_ids = set([job.id for job in scheduler.get_jobs()])
    app.logger.debug('[running_job_ids] %s' % ','.join(running_job_ids))
    available_job_ids = set()
    # add new job to schedule
    for job_instance in JobInstance.query.filter_by(enabled=0, run_type="periodic").all():
        job_id = "spider_job_%s:%s" % (job_instance.id, int(time.mktime(job_instance.date_modified.timetuple())))
        available_job_ids.add(job_id)
        if job_id not in running_job_ids:
            scheduler.add_job(run_spider_job,
                              args=(job_instance,),
                              trigger='cron',
                              id=job_id,
                              minute=job_instance.cron_minutes,
                              hour=job_instance.cron_hour,
                              day=job_instance.cron_day_of_month,
                              day_of_week=job_instance.cron_day_of_week,
                              month=job_instance.cron_month,
                              second=0)
            app.logger.info('[load_spider_job][project:%s][spider_name:%s][job_instance_id:%s][job_id:%s]' % (
                job_instance.project_id, job_instance.spider_name, job_instance.id, job_id))
    # remove invalid jobs
    for invalid_job_id in filter(lambda job_id: job_id.startswith("spider_job_"),
                                 running_job_ids.difference(available_job_ids)):
        scheduler.remove_job(invalid_job_id)
        app.logger.info('[drop_spider_job][job_id:%s]' % invalid_job_id)


def scheduler_error_listener(ev):
    if ev.exception:
        app.logger.error('[%s]\n[%s]', ev.job_id, ev.traceback)
        db.session.rollback()
        db.session.remove()
    else:
        app.logger.error('[%s][missed]' % ev.job_id)
