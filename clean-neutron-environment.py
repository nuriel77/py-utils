#!/usr/bin/env python
from keystoneauth1 import identity
from keystoneauth1 import session
from neutronclient.v2_0 import client
from subprocess import call
from os import environ
import sys


""" Remove all neutron network components """
class Networks():

    def __init__(self, neutron):
        self.neutron = neutron

    def start_cleanup(self):
        self.delete_floatingips()
        self.clear_router_gws()
        self.delete_routers()
        self.delete_ports()
        self.delete_subnets()
        self.delete_networks()
        self.delete_subnetpools()
        self.delete_address_scopes()

    @property
    def get_address_scopes(self):
        address_scopes = self.neutron.list_address_scopes()
        return address_scopes['address_scopes']

    @property
    def get_floatingips(self):
        floatingips = self.neutron.list_floatingips()
        return floatingips['floatingips']

    @property
    def get_ports(self):
        ports = self.neutron.list_ports()
        return ports['ports']

    @property
    def get_routers(self):
        routers = self.neutron.list_routers()
        return routers['routers']

    @property
    def get_subnets(self):
        subnets = self.neutron.list_subnets()
        return subnets['subnets']

    @property
    def get_networks(self):
        networks = self.neutron.list_networks()
        return networks['networks']

    @property
    def get_subnetpools(self):
        subnet_pools = self.neutron.list_subnetpools()
        return subnet_pools['subnetpools']

    def delete_address_scopes(self):
        address_scopes = self.get_address_scopes
        for address_scope in address_scopes:
            log("Delete address scope '%s'" % address_scope['id'])
            self.neutron.delete_address_scope(address_scope['id'])

    def delete_subnetpools(self):
        subnet_pools = self.get_subnetpools
        for subnet_pool in subnet_pools:
            log("Delete subnetpool '%s'" % subnet_pool['id'])
            self.neutron.delete_subnetpool(subnet_pool['id'])

    def delete_networks(self):
        networks = self.get_networks
        for network in networks:
            log("Delete network '%s'" % network['id'])
            self.neutron.delete_network(network['id'])

    def delete_subnets(self):
        subnets = self.get_subnets
        for subnet in subnets:
            log("Delete subnet '%s'" % subnet['id'])
            self.neutron.delete_subnet(subnet['id'])

    def clear_router_gws(self):
        routers = self.get_routers
        for router in routers:
            log("Clear gateway from router '%s'" % router['id'])
            self.neutron.remove_gateway_router(router['id'])

    def delete_routers(self):
        routers = self.get_routers
        subnets = self.get_subnets
        for router in routers:
            for subnet in subnets:
                cmd = "neutron router-interface-delete %s %s" % \
                    (router['id'], subnet['id'])
                try:
                    call([cmd], shell=True)
                except OSError as e:
                    log("OSError > ", e.errno)
                    log("OSError > ", e.strerror)
                    log("OSError > ", e.filename)
                except:
                    log("Error > ", sys.exc_info()[0])
                else:
                    log("Removed subnet '%s' from router '%s'" %
                        (subnet['id'], router['id']))

            log("Delete router '%s'" % router['id'])
            self.neutron.delete_router(router['id'])

    def delete_ports(self):
        ports = self.get_ports
        for port in ports:
            log("Delete port '%s'" % port['id'])
            self.neutron.delete_port(port['id'])

    def delete_floatingips(self):
        floatingips = self.get_floatingips
        for floatingip in floatingips:
            log("Delete floating IP '%s'" % floatingip['floating_ip_address'])
            self.neutron.update_floatingip(floatingip['id'],
                {'floatingip': {'port_id': None}})
            self.neutron.delete_floatingip(floatingip['id'])


def log(msg):
  sys.stderr.write(msg + '\n')


def main():

    try:
        environ['OS_CLOUDNAME']
    except:
        pass
    else:
        if environ['OS_CLOUDNAME'] == 'undercloud':
            log("Undercloud auth details loaded."
                " Make sure you load overcloudrc!")
            sys.exit(1)

    try:
        environ['OS_TENANT_NAME']
    except Exception as e:
        try:
            environ['OS_PROJECT_NAME']
        except Exception as e:
            raise Exception("Did not find OS_PROJECT_NAME!"
                            " Missing authentication details.")
        else:
            environ['OS_TENANT_NAME'] = environ['OS_PROJECT_NAME']

    try:
        environ['OS_TENANT_NAME']
        environ['OS_PASSWORD']
        environ['OS_USERNAME']
        environ['OS_AUTH_URL']
    except Exception as e:
        raise Exception('Missing authentication credentials: %s' % e)

    username = environ['OS_USERNAME']
    password = environ['OS_PASSWORD']
    project_name = environ['OS_TENANT_NAME']
    auth_url = environ['OS_AUTH_URL']

    auth = identity.Password(auth_url=auth_url,
                             username=username,
                             password=password,
                             project_name=project_name)

    sess = session.Session(auth=auth)
    neutron = client.Client(session=sess)
    try:
        Networks(neutron).start_cleanup()
    except Exception as e:
        raise Exception(e)


if __name__ == "__main__":
    main()
