#!/usr/bin/env python
import traceback
import subprocess
import argparse
import logging
import sys
import os
import re

try:
    import xml.etree.ElementTree as ET
except ImportError:
    import elementtree.ElementTree as ET


""" Check for pacemaker cluster health
    Also checks resources and history
    Can verify stonith configuration
    Nuriel Shem-Tov <nurielst@hotmail.com>
"""


LOG = logging.getLogger(__name__)


# Return codes for resource tasks
# Source: clusterlabs.org/doc/en-US/Pacemaker/1.1/html/Pacemaker_Explained/s-ocf-return-codes.html  # noqa
OCF_RETURN_CODES = {
    0:  'OCF_SUCCESS',
    1:  'OCF_ERR_GENERIC',
    2:  'OCF_ERR_ARGS',
    3:  'OCF_ERR_UNIMPLEMENTED',
    4:  'OCF_ERR_PERM',
    5:  'OCF_ERR_INSTALLED',
    6:  'OCF_ERR_CONFIGURED',
    7:  'OCF_NOT_RUNNING',
    8:  'CCF_RUNNING_MASTER',
    9:  'OCF_FAILED_MASTER'
}


class CRMBaseObject(object):

    def __init__(self, xml_obj):
        self.xml_obj = xml_obj
        for k, v in xml_obj.attrib.iteritems():
            setattr(self, k, v)

    @classmethod
    def get_instances(cls):
        return list(cls.instances)

    @classmethod
    def count(cls):
        return len(cls.instances)


class Resources(CRMBaseObject):
    instances = []

    def __init__(self, obj):
        CRMBaseObject.__init__(self, obj)
        Resources.instances.append(self)

    @classmethod
    def clean(cls):
        del cls.instances[:]


class Clones(CRMBaseObject):
    instances = []

    def __init__(self, obj):
        CRMBaseObject.__init__(self, obj)
        Clones.instances.append(self)


class Nodes(CRMBaseObject):
    instances = []

    def __init__(self, obj):
        CRMBaseObject.__init__(self, obj)
        Nodes.instances.append(self)

    def set_history(self, obj):
        self.history = obj

    @property
    def get_history(self):
        return self.history


def parse_args():
    parser = argparse.ArgumentParser(
        description='Check Pacemaker cluster')

    parser.add_argument('--crm_mon', metavar='bin', type=str,
                        default='/sbin/crm_mon',
                        help='crm_mon binary. Defaults to '
                             '/sbin/crm_mon')

    parser.add_argument('--pcs', metavar='bin', type=str,
                        default='/sbin/pcs',
                        help='pcs binary, defaults to '
                             '/sbin/pcs')

    parser.add_argument('--debug', '-d', action='store_true',
                        help='Debug output')

    parser.add_argument('--resource', metavar='name', type=str,
                        help='Check for specific resource')

    parser.add_argument('--stonith', action='store_true',
                        help='Check stonith enable')

    parser.add_argument('--stonith-agent', metavar='agent',
                        default='stonith:fence_ipmilan',
                        help='Stonith agent name to check for'
                             ' (default: stonith:fence_ipmilan)'
                             ' Only works with --stonith')

    parser.add_argument('--history', action='store_true',
                        help='Check past resource events')

    return parser.parse_args()


def get_crm_output(binary):
    try:
        crm = subprocess.Popen([binary, '-r', '-1', '-X'],
                               stdout=subprocess.PIPE)
    except OSError as e:
        sys.stderr.write("Error: %s" % e)
        sys.exit(2)

    stdout, __ = crm.communicate()
    try:
        root = ET.fromstring(stdout)
    except Exception as e:
        sys.stderr.write("Error parsing XML output: %s" % e)
        sys.exit(2)

    return root


def check_maintenance(binary):
    try:
        crm = subprocess.Popen([binary + ' property|grep maintenance'],
                               stdout=subprocess.PIPE, shell=True)
    except OSError as e:
        sys.stderr.write("Error: %s" % e)
        sys.exit(2)

    stdout, __ = crm.communicate()
    LOG.debug('Maintenance mode output: %s' % stdout.rstrip())
    if re.match(r'.*maintenance-mode: true.*', stdout):
        print "Warning: Cluster in maintenance mode!"
        sys.exit(1)


def set_logger(debug=False):
    if debug is True:
        LOG.setLevel(logging.DEBUG)
    else:
        LOG.setLevel(logging.INFO)

    ch = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    ch.setFormatter(formatter)
    LOG.addHandler(ch)
    LOG.debug('Set debug level')


def check_cluster():
    try:
        args = parse_args()
    except Exception as e:
        sys.stderr.write("Error parsing arguments: %s\n" % e)
        sys.exit(1)

    if not os.path.exists(args.crm_mon):
        sys.stderr.write("Error: %s not found\n" % args.crm_mon)
        sys.exit(3)

    if not os.path.exists(args.pcs):
        sys.stderr.write("Error: %s not found\n" % args.pcs)
        sys.exit(3)

    set_logger(debug=args.debug)

    # Check if maintenance mode is set for
    # the entire cluster. Exit warning if so.
    check_maintenance(args.pcs)

    # Get XML output
    try:
        root = get_crm_output(args.crm_mon)
    except:
        sys.stderr.write(traceback.format_exc())
        sys.exit(2)

    # Sort data into objects
    for obj in root.find('nodes').findall('node'):
        LOG.debug('Creating Node instance: %s' % ET.tostring(obj))
        Nodes(obj)

    for obj in root.find('resources').findall('resource'):
        LOG.debug('Creating Resource instance: %s' %
                  ET.tostring(obj))
        Resources(obj)

    for obj in root.find('resources').findall('clone'):
        LOG.debug('Creating Clone resource instance: %s' %
                  ET.tostring(obj))
        Clones(obj)

    node_history = root.find('node_history')
    for node in Nodes.get_instances():
        obj = node_history.find(".node[@name='%s']" % node.name)
        LOG.debug('Appending Node instance history: %s' %
                  ET.tostring(obj))
        node.set_history(obj)

    rc = 0

    # Check node count
    summary = root.find('summary')
    nodes_configured = summary.find('nodes_configured').attrib['number']
    if int(nodes_configured) > Nodes.count():
        LOG.warning("Missing nodes from configuration")
        rc = 1

    # Check stonith enabled
    stonith = summary.find('cluster_options').attrib['stonith-enabled']
    if stonith != "true" and args.stonith is True:
        LOG.warning("Stonith disabled!")
        rc = 1

    # Check node status
    standby_nodes = 0
    maintenance_nodes = 0
    stonith_nodes = 0
    for node in Nodes.get_instances():
        if args.resource:
            continue

        if node.maintenance == "true":
            LOG.info("Node %s is in maintenance mode" % node.name)
            maintenance_nodes += 1
            continue

        if node.standby == "true":
            LOG.info("Node %s is in standby mode" % node.name)
            standby_nodes += 1
            continue

        if node.online != "true":
            LOG.error("Node %s is not online" % node.name)
            rc = 2
            continue

        if node.unclean == "true":
            LOG.warning("Node %s unclean" % node.name)
            rc = 1

        if not args.history:
            continue

        rh_all = node.get_history.findall("resource_history")
        for rh in rh_all:
            opsh = rh.findall('operation_history')
            for op in opsh:
                if op.attrib['rc'] != "0" and op.attrib['rc'] != "8":
                    LOG.warning("Node %s resource %s task"
                          " %s had return code %s (%s)"
                          " last seen at %s" %
                          (node.name,
                           rh.attrib['id'],
                           op.attrib['task'],
                           op.attrib['rc'],
                           OCF_RETURN_CODES[op.attrib['rc']],
                           op.attrib['last-rc-change']))
                    if rc == 0:
                        rc = 1

    resource_found = False
    for resource in Resources.get_instances():
        if args.resource and args.resource != resource.id:
            continue

        resource_found = True
        node = "N/A"
        try:
            node = resource.xml_obj.find('node').attrib['name']
        except:
            pass

        if resource.active != "true" or resource.failure_ignored == "true":
            continue

        if resource.role != "Started":
            LOG.error("Resource '%s' not Started on node %s" %
                      (resource.id, node))
            rc = 2

        if resource.failed == "true":
            LOG.error("Resource '%s' failed on node %s" %
                      (resource.id, node))
            rc = 2

        if resource.managed == "false":
            LOG.warning("Resource '%s' not managed on node %s" %
                  (resource.id, node))
            if rc == 0:
                rc = 1

        if args.resource:
            LOG.info("Resource %s started on %s" % (resource.id, node))

        if resource.resource_agent == args.stonith_agent:
            stonith_nodes += 1

    for clone in Clones.get_instances():
        if args.resource and args.resource != clone.id:
            continue

        resource_found = True
        if clone.failed == "true" and clone.failure_ignored != "false":
            rc = 2
            LOG.error("Clone '%s' on node %s failed" % (clone.id, node))

        Resources.clean()
        for obj in clone.xml_obj.findall('resource'):
            r = Resources(obj)
            if r.role == "Stopped":
                LOG.error("Clone resource is stopped: %s" % r.id)
                rc = 2
                continue

            node = r.xml_obj.find('node').attrib['name']
            if r.active != "true" or r.failure_ignored == "true":
                continue

            if r.failed == "true":
                LOG.error("Clone '%s' resource '%s' failed on node %s" %
                          (clone.id, r.id, node))
                rc = 2

            if clone.managed == "false":
                LOG.warning("Clone '%s' resource '%s' not managed "
                            "on node %s" %
                            (clone.id, r.id, node))
                if rc == 0:
                    rc = 1

            if args.resource:
               LOG.info("Resource clone %s started on %s" % (r.id, node))

    if args.stonith and args.stonith_agent:
        if stonith_nodes < Nodes.count():
            if stonith_nodes == 0:
                LOG.warning("No stonith nodes")
            else:
                LOG.warning("%s stonith nodes configured out of %s nodes" %
                      (stonith_nodes, Nodes.count()))
            if rc == 0:
                rc = 1

    def percentage(part, whole):
        return 100 * float(part)/float(whole)

    perc_maint = percentage(maintenance_nodes, Nodes.count())
    perc_standby = percentage(standby_nodes, Nodes.count())
    if perc_maint > 50:
        LOG.warning("More than half of the cluster nodes"
              " are in maintenance (%.1f)" % perc_maint)
        if rc == 0:
            rc = 1

    if perc_standby > 50:
        LOG.warning("More than half of the cluster nodes"
              " are in standby mode (%.1f)" % perc_standby)
        if rc == 0:
            rc = 1

    if args.resource and resource_found is False:
        LOG.error("Did not find resource %s" % args.resource)
        rc = 2

    if rc == 0:
        LOG.info("Cluster health OK")

    return rc


if __name__ == "__main__":
    sys.exit(check_cluster())
