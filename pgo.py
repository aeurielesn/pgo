import os
import sys
import time
import logging
import logging.config
from datetime import datetime, timedelta
import praw
from ConfigParser import SafeConfigParser
import json
from jinja2 import Environment, PackageLoader


class WEEKDAY(object):
    MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


class Statistics(object):
    def __init__(self):
        super(Statistics, self).__init__()
        self.untagged_posts = 0
        self.all_posts = 0
        self.ignored_posts = 0
        self.removed_posts = 0

    def dump(self):
        logging.info("untagged_posts: {0}".format(self.untagged_posts))
        logging.info("all_posts: {0}".format(self.all_posts))
        logging.info("ignored_posts: {0}".format(self.ignored_posts))
        logging.info("removed_posts: {0}".format(self.removed_posts))


class Views(object):
    def __init__(self, path):
        super(Views, self).__init__()
        self.templates = {}
        self.env = Environment(loader=PackageLoader('pgo', path))

    def render(self, template, *args, **kwargs):
        if not template in self.templates:
            self.templates[template] = self.env.get_template('{0}.tpl'.format(template))

        return self.templates[template].render(**kwargs)


class PGO(object):
    def __init__(self, config_file):
        super(PGO, self).__init__()
        self.config_file = config_file

    def _load_config(self):
        cfg = SafeConfigParser()
        cfg_path = os.path.abspath(os.path.dirname(sys.argv[0]))
        cfg_path = os.path.join(cfg_path, self.config_file)
        cfg.read(cfg_path)
        return cfg

    def _save_config(self, cfg):
        cfg_path = os.path.abspath(os.path.dirname(sys.argv[0]))
        cfg_path = os.path.join(cfg_path, self.config_file)
        cfg.write(open(cfg_path, 'w'))

    def _setup(self):
        logging.config.fileConfig(self.config_file)
        self.stats = Statistics()
        self.r = praw.Reddit(user_agent="pgo/1.0")
        self.cfg = self._load_config()
        self.views = Views("templates")

    def _reddit_login(self):
        while True:
            try:
                logging.info(u'Logging in as {0}'.format(self.cfg.get('reddit', 'username')))
                self.r.login(self.cfg.get('reddit', 'username'), self.cfg.get('reddit', 'password'), disable_warning=True)
                break
            except Exception as e:
                logging.error('ERROR: {0}'.format(e))

    def _check_conditions(self, submission, link_flairs):
        if datetime.utcfromtimestamp(submission.created_utc).weekday() not in [WEEKDAY.SATURDAY, WEEKDAY.SUNDAY]:
            if not submission.approved_by and not submission.banned_by:
                if submission.link_flair_text and submission.link_flair_text.lower() in link_flairs:
                    return True
        return False

    def _remove_submission(self, submission):
        submission.remove(False)
        comment = self.views.render("screenshots")
        response = submission.add_comment(comment)
        response.distinguish()

    def _process_submissions(self):
        logging.info(u'Serving at /r/{0}'.format(self.cfg.get('reddit', 'subreddit')))
        last_update = datetime.utcnow() - timedelta(hours=24)
        backlog_seconds = int(self.cfg.get('reddit', 'backlog_seconds'))
        refresh_seconds = int(self.cfg.get('reddit', 'refresh_seconds'))
        link_flairs = json.loads(self.cfg.get('reddit', 'link_flairs'))

        while True:
            try:
                new_update = last_update
                sr = self.r.get_subreddit(self.cfg.get('reddit', 'subreddit'))
                submissions = sr.get_new(limit=None)
                fresh_submissions_threshold = datetime.utcnow() - timedelta(seconds=backlog_seconds)
                for submission in submissions:
                    submission_time = datetime.utcfromtimestamp(submission.created_utc)

                    if submission_time > fresh_submissions_threshold:
                        logging.info(u"FRESH: {0}".format(submission.title))
                        continue

                    if submission_time <= last_update:
                        break

                    new_update = max(new_update, submission_time)

                    if not submission.link_flair_text:
                        self.stats.untagged_posts += 1

                    self.stats.all_posts += 1

                    if self._check_conditions(submission, link_flairs):
                        logging.info(u"REMOVE: {0}".format(submission.title))
                        self._remove_submission(submission)
                        self.stats.removed_posts += 1
                    else:
                        logging.info(u"IGNORE: {0}".format(submission.title))
                        self.stats.ignored_posts += 1

                # save new last_update value
                # if new_update > last_update:
                #     self.cfg.set('reddit', 'last_update', str(last_update))
                #     self._save_config(self.cfg)

                last_update = new_update
                logging.info(u"last_update: {0}".format(last_update))
                self.stats.dump()

                logging.info('Sleeping for {0} seconds'.format(refresh_seconds))
                time.sleep(refresh_seconds)
                logging.info('Sleep ended, resuming')
            except Exception as e:
                logging.error('ERROR: {0}'.format(e))

    def serve(self):
        logging.info("Starting")
        self._setup()
        self._reddit_login()
        self._process_submissions()

if __name__ == '__main__':
    PGO("pgo.cfg").serve()
