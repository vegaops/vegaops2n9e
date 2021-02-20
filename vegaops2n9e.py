# -*- coding: UTF-8 -*-
import json
import logging
import os
import re
import requests
import schedule
import sys
import threading
import time
import yaml


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('VegaOps2N9e')

reload(sys)
sys.setdefaultencoding('utf8')


def _push_metrics(cfg, metrics):
    headers = {
        "X-User-Token": cfg.get('token'),
        "Content-Type": "Application/json"
    }
    url = cfg.get('url', {}).get('base')
    if not url:
        raise Exception("N9E URL could not be empty.")
    uri = url + '/api/transfer/push'
    resp = requests.post(uri, headers=headers, data=json.dumps(metrics))
    if resp.status_code not in [200, 201]:
        logger.error(resp.text)
        raise Exception("Bad request status[%s] for "
                        "%s" % (resp.status_code, uri))
    cont = resp.json()
    if cont.get('err'):
        logger.error(resp.text)


def _register_resource(cfg, resource):
    headers = {
        "X-User-Token": cfg.get('token'),
        "Content-Type": "Application/json"
    }
    url = cfg.get('url', {}).get('rdb')
    if not url:
        raise Exception("N9E URL could not be empty.")
    uri = url + '/v1/rdb/resources/register'
    resp = requests.post(uri, headers=headers, data=json.dumps(resource))
    if resp.status_code not in [200, 201]:
        logger.error(resp.text)
        raise Exception("Bad request status[%s] for "
                        "%s" % (resp.status_code, uri))
    cont = resp.json()
    if cont.get('err'):
        logger.error(resp.text)


def _build_item(item, key):
    if not isinstance(key, (str, unicode)):
        return key
    if key.startswith('vm.'):
        return item.get(key[3:])
    return key


def _build_metrics(res, target):
    metrics = []
    for item in res:
        metric = {}
        for key in target:
            if isinstance(target[key], (dict, list)):
                tmp = {}
                for kk in target[key]:
                    val = _build_item(item, target[key][kk])
                    tmp[kk] = val
                metric[key] = json.dumps(tmp)
            else:
                val = _build_item(item, target[key])
                metric[key] = val
        metrics.append(metric)
    return metrics


def _build_resources(res, target):
    resources = []
    for item in res:
        resource = {}
        for key in target:
            if isinstance(target[key], (dict, list)):
                tmp = {}
                for kk in target[key]:
                    val = _build_item(item, target[key][kk])
                    tmp[kk] = val
                resource[key] = json.dumps(tmp)
            else:
                val = _build_item(item, target[key])
                resource[key] = val
        resources.append(resource)
    return resources


def _job(n9e, polling):
    if polling.get('type', 'resource') == 'resource':
        _job_resource(n9e, polling)
    elif polling.get('type', 'resource') == 'metric':
        _job_metric(n9e, polling)


def _job_metric(n9e, polling):
    if not os.path.exists('./tasks'):
        os.system('mkdir -p ./tasks')
    regions = polling.get('regions', [])
    for region in regions:
        task = "%s_%s" % (polling.get('task'), region.get('name'))
        logger.info("Start to run task: %s" % task)
        task_file = './tasks/Task-%s.yaml' % task
        output_dir = './tasks/%s' % task
        task_d = {
            "componentId": task,
            "credentials": polling.get('credentials', {}),
            "vendor": polling.get('vendor'),
            "version": polling.get('version'),
            "nodes": polling.get('nodes', [])
        }
        task_d['credentials']['regionId'] = region.get('name')
        try:
            fd = open(task_file, "w")
            yaml.dump(task_d, fd)
        except Exception as e:
            logger.error("Failed to create task file %s" % task)
        if not os.path.exists(output_dir):
            os.system('mkdir %s' % output_dir)
        os.system('/opt/vegaops/bin/vegaops %s %s' % (task_file, output_dir))
        output = '%s/out.yaml' % output_dir
        if not os.path.isfile(output):
            logger.error("Could not find output file %s" % output)
            return
        try:
            out = yaml.safe_load(open(output, 'r').read())
        except Exception as e:
            logger.error("Failed to load output as %s" % e)
            return
        for node in polling.get('nodes', []):
            target = node.get('target')
            component = node.get('componentId')
            if component not in out:
                continue
            if not out[component].get('success'):
                continue
            dt = out[component].get('resultType')
            if not dt.startswith('list:'):
                continue
            metrics = _build_metrics(
                    out[component].get(dt[5:], []), target)
            if not len(metrics):
                continue
            _push_metrics(n9e, metrics)


def _job_resource(n9e, polling):
    if not os.path.exists('./tasks'):
        os.system('mkdir -p ./tasks')
    regions = polling.get('regions', [])
    for region in regions:
        task = "%s_%s" % (polling.get('task'), region.get('name'))
        logger.info("Start to run task: %s" % task)
        task_file = './tasks/Task-%s.yaml' % task
        output_dir = './tasks/%s' % task
        task_d = {
            "componentId": task,
            "credentials": polling.get('credentials', {}),
            "vendor": polling.get('vendor'),
            "version": polling.get('version'),
            "nodes": polling.get('nodes', [])
        }
        task_d['credentials']['regionId'] = region.get('name')
        if not os.path.isfile(task_file):
            try:
                fd = open(task_file, "w")
                yaml.dump(task_d, fd)
            except Exception as e:
                logger.error("Failed to create task file %s" % task)
        if not os.path.exists(output_dir):
            os.system('mkdir %s' % output_dir)
        os.system('/opt/vegaops/bin/vegaops %s %s' % (task_file, output_dir))
        output = '%s/out.yaml' % output_dir
        if not os.path.isfile(output):
            logger.error("Could not find output file %s" % output)
            return
        try:
            out = yaml.safe_load(open(output, 'r').read())
        except Exception as e:
            logger.error("Failed to load output as %s" % e)
            return
        for node in polling.get('nodes', []):
            target = node.get('target')
            component = node.get('componentId')
            if component not in out:
                continue
            if not out[component].get('success'):
                continue
            dt = out[component].get('resultType')
            if not dt.startswith('list:'):
                continue
            resources = _build_resources(
                    out[component].get(dt[5:], []), target)
            if not len(resources):
                continue
            _register_resource(n9e, resources)


def _run_threaded(cfg):
    job_thread = threading.Thread(
            target=cfg['func'], args=(cfg['n9e'], cfg['job']))
    job_thread.start()


def _load_jobs(config):
    pollings = config.get('pollings', [])
    for polling in pollings:
        cfg = {
            'n9e': config.get('n9e', {}),
            'job': polling,
            'func': _job
        }
        schedule.every(
            polling.get('interval', 1800)).seconds.do(_run_threaded, cfg)
        # _job(cfg['n9e'], cfg['job'])


def cron_job(config):
    _load_jobs(config)
    while True:
        schedule.run_pending()
        time.sleep(1)


def once_job(config):
    pass


def main():
    argv = sys.argv
    config_path = "./config.yaml"
    _type = 'cron'
    if len(argv) <= 1:
        logger.info("Use %s as config file" % config_path)
    else:
        config_path = argv[1]
    if not os.path.isfile(config_path):
        logger.error("Could not find file %s" % config_path)
        os.exit(1)
    if len(argv) >= 3:
        _type = argv[2]
    try:
        config = yaml.safe_load(open(config_path, 'r').read())
    except Exception as e:
        logger.error("Faild to load config file as "
                      "error %s" % e)
        raise e
    if _type == 'cron':
        cron_job(config)
    elif _type == 'once':
        once_job(config)
    else:
        logger.error("Bad job type %s, only support "
                      "cron, once job" % _type)
        os.exit(1)


if __name__ == "__main__":
    main()
