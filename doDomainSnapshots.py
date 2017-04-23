#!/usr/bin/env python
import argparse
import libvirt
import logging
import time
import sys
import os
from pprint import pformat
from heapq import nlargest

try:
    import xml.etree.ElementTree as ET
except ImportError:
    import elementtree.ElementTree as ET


LOG = logging.getLogger(__name__)


""" C style enumeration flags for create snapshot.
    Source: https://libvirt.org/html/libvirt-libvirt-domain-snapshot.html#virDomainSnapshotCreateFlags
    Some features like disk snapshot only or live snapshot
    are not supported by the default version of qemu binary
    shipped by Centos.
    For other versions check rdo-qemu-ev repo
"""
virDomainSnapshotCreateFlags = {
        1:   'VIR_DOMAIN_SNAPSHOT_CREATE_REDEFINE:     restore or alter metadata',
        2:   'VIR_DOMAIN_SNAPSHOT_CREATE_CURRENT:      with redefine, make snapshot current',
        4:   'VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA:  make snapshot without remembering it',
        8:   'VIR_DOMAIN_SNAPSHOT_CREATE_HALT:         stop running guest after snapshot',
        16:  'VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY:   disk snapshot, not system checkpoint',
        32:  'VIR_DOMAIN_SNAPSHOT_CREATE_REUSE_EXT:   reuse any existing external files',
        64:  'VIR_DOMAIN_SNAPSHOT_CREATE_QUIESCE:     use guest agent to quiesce all mounted file systems within the domain',
        128: 'VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC:     atomically avoid partial changes',
        256: 'VIR_DOMAIN_SNAPSHOT_CREATE_LIVE:       create the snapshot while the guest is running'
    }

virDomainSnapshotDeleteFlags = {
        1: 'VIR_DOMAIN_SNAPSHOT_DELETE_CHILDREN:      Also delete children (exclusive flag)',
        2: 'VIR_DOMAIN_SNAPSHOT_DELETE_METADATA_ONLY: Delete just metadata',
        4: 'VIR_DOMAIN_SNAPSHOT_DELETE_CHILDREN_ONLY: Delete just children (exclusive flag)'
    }


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description='Create a snapshot for a domain.',
        epilog="""Examples:

Snapshot 'snap_test' and keep one most-recent snapshot
{0} --domain snap_test --keep 1 --snapshot-name "mytest"

Snapshot 'snap_test' and keep no recent snapshots'
{0} --domain snap_test --keep 0

Snapshot 'snap_test' and keep 3 most-recent snapshots.
In addition use snapshot creation flags
{0} --domain snap_test --keep 3 --flags 8+16+128

Snapshot 'snap_test' and keep 3 most-recent snapshots.
In addition use snapshot creation and deletion flags
{0} --domain snap_test --keep 3 --flags 152 --del-flags 4
""".format(sys.argv[0]))

    parser.add_argument('--snapshot-xml', metavar='xml',
                        type=snapshot_xml_type,
                        help="""Custom snapshot XML definition.
Will override snapshot name and description if provided.
File or XML tree. Example:
https://libvirt.org/formatsnapshot.html#example""")

    parser.add_argument('--qemu-uri', metavar='uri', type=str,
                        default='qemu:///system',
                        help='Libvirt/Qemu connection URI. Default: %(default)s')

    parser.add_argument('--domain', metavar='name', type=str,
                        required=True,
                        help='Domain name to snapshot.')

    parser.add_argument('--keep', metavar='int', type=int,
                        default=2,
                        help='Number of snapshots to keep, excluding the new one.'
                             ' Will delete older ones. Default: %(default)s')

    parser.add_argument('--debug', '-d', action='store_true',
                        help='Debug output')

    parser.add_argument('--snapshot-name', '-n', type=str,
                        help='Snapshot name. Defaults to unix time')

    parser.add_argument('--desc', type=str,
                        default='DomSnapshot script',
                        help='Snapshot description. Default: %(default)s')

    parser.add_argument('--del-flags', type=snapshot_flags_del_type,
                        default=0,
                        help='''Bitmask choices, c-style: provide string
Representing choices or the sum, e.g. syntax 1+8+16. Used for snapshot deletion.
%s''' % pformat(virDomainSnapshotDeleteFlags, width=80,indent=2))

    parser.add_argument('--flags', type=snapshot_flags_type,
                        default=0,
                        help='''Bitmask choices, c-style: provide string
Representing choices or the sum, e.g. syntax 1+8+16. Used for snapshot creation. 
%s''' % pformat(virDomainSnapshotCreateFlags, width=80,indent=2))

    return parser.parse_args()


def snapshot_flags_del_type(flags):
    try:
        values = [int(v) for v in flags.split('+')]
    except Exception as e:
        LOG.error("Error in delete flag values: %s\n" %e)
        raise
    vsum = sum(values)
    if vsum > sum(virDomainSnapshotDeleteFlags.keys()) or vsum < 0:
        LOG.error("Delete flag values out of range\n")
        raise

    LOG.debug('Delete flags sum: %d' % vsum)
    return vsum


def snapshot_flags_type(flags):
    try:
        values = [int(v) for v in flags.split('+')]
    except Exception as e:
        LOG.error("Error in flag values: %s\n" %e)
        raise
    vsum = sum(values)
    if vsum > sum(virDomainSnapshotCreateFlags.keys()) or vsum < 0:
        LOG.error("Flag values out of range\n")
        raise

    LOG.debug('Create flags sum: %d' % vsum)
    return vsum


def snapshot_xml_type(xml):
    if os.path.exists(xml) and os.path.isfile(xml):
       try:
           tree = ET.parse(xml)
           root = tree.getroot()
       except Exception as e:
           LOG.error("Invalid XML file\n")
           raise
       LOG.debug('Loaded XML from file')
    else:
        try:
            root = ET.fromstring(xml)
        except Exception as e:
            LOG.error("Invalid XML or file not found\n")
            raise
        LOG.debug('Loaded XML from string')
    return root  


def delete_older_snapshots(dom, keep, flags=0):
    c_times = {}
    snap_list = dom.snapshotListNames()
    for name in snap_list:
        try:
            snapshot = dom.snapshotLookupByName(name)
        except Exception as e:
            LOG.warning("Skip item, not found? %s" % e)
            continue
        root = ET.fromstring(snapshot.getXMLDesc())
        c_time = root.find('creationTime').text
        c_times[c_time] = name

    # Keep the newest n number of snapshots 
    to_keep = nlargest(keep, c_times)
    for remove_newest in to_keep:
        LOG.debug("Exclude newer snapshot '%s' time %s" %
                  (c_times[remove_newest],
                   time.strftime('%Y-%m-%d %H:%M:%S',
                                 time.localtime(int(remove_newest))
                                )
                  ))

        del c_times[remove_newest]

    for c_time, name in c_times.items():
        LOG.debug('Get snapshot %s object' % name)
        try:
            snapshot = dom.snapshotLookupByName(name)
        except Exception as e:
            LOG.warning("Skip item, not found? %s" % e)
            continue
        LOG.info("Delete snapshot '%s' time %s" % (name,
                 time.strftime('%Y-%m-%d %H:%M:%S',
                               time.localtime(int(c_time))
                              )
                ))
        try:
            snapshot.delete(flags=flags) 
        except Exception as e:
            LOG.error("Failed to delete snapshot %s: %s" %
                      (name, e))


def connect_libvirt(qemu_uri):
    # Connect to libvirt
    conn = libvirt.open(qemu_uri)
    if conn is None:
        LOG.error('Failed to open connection to the hypervisor\n')
        sys.exit(1)

    return conn


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


def do_snapshot():
    try:
        args = parse_args()
    except Exception as e:
        sys.stderr.write("Error parsing arguments: %s\n" % e)
        sys.exit(1)

    # Set logger config
    set_logger(debug=args.debug)

    # Connect to libvirt
    conn = connect_libvirt(args.qemu_uri)
    try:
        dom = conn.lookupByName(args.domain)
    except libvirt.libvirtError:
        LOG.error("Domain %s not found?\n" % args.domain)
        sys.exit(1)
    LOG.debug('Connected to libvirt')

    # Delete older snapshots
    delete_older_snapshots(dom, keep=args.keep, flags=args.del_flags)

    # Prepare snapshot XML
    snap_name = args.snapshot_name if args.snapshot_name else int(time.time())
    if not args.snapshot_xml:
        snapshot_xml = """<domainsnapshot>
                            <description>%s</description>
                            <name>%s</name>
                          </domainsnapshot>""" % \
                       (args.desc, snap_name)
    LOG.debug("Snapshot XML: %s" % snapshot_xml)

    LOG.info('Snapshotting domain %s' % dom.name())
    try:
        snapshot = dom.snapshotCreateXML(snapshot_xml, flags=args.flags)
    except Exception as e:
        LOG.error("Error snapshotting: %s" % e)
        sys.exit(1)

    LOG.debug(snapshot.getXMLDesc())
    LOG.info("Snapshot %s for %s created successfully" %
             (snap_name, dom.name()))


if __name__ == "__main__":
    do_snapshot()
