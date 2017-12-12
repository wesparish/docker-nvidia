#!/usr/bin/python

"""
Pushes nVidia GPU metrics to a Prometheus Push gateway for later collection.
"""

import argparse
import logging
import time
import platform

import socket
import os
import urllib2
import json
import importlib

from prometheus_client import CollectorRegistry, Gauge, Counter, push_to_gateway
from prometheus_client import start_http_server, core
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY

from pynvml import *

import NVMLCollector

log = logging.getLogger('miner-wrapper')

def _create_parser():
	parser = argparse.ArgumentParser(description='nVidia GPU Prometheus Metrics Exporter')
	parser.add_argument('--verbose',
						help='Turn on verbose logging',
						action='store_true')

	parser.add_argument('-u', '--update-period',
						help='Period between calls to update metrics, '
							 'in seconds. Defaults to 30.',
						default=30)

	parser.add_argument('-g', '--gateway',
						help='If defined, gateway to push metrics to. Should '
							 'be in the form of <host>:<port>.',
						default=None)

	parser.add_argument('-cp', '--collector-port',
						help='If non-zero, port to run the collector http server',
						type=int,
						default=0)

	parser.add_argument('-mm', '--miner-module',
						help='miner python module',
						required=True)

	parser.add_argument('-mh', '--miner-host',
						help='miner API hostname',
						default="localhost")

	parser.add_argument('-mp', '--miner-port',
						help='miner API tcp port',
						type=int,
						required=True)
	return parser

def collect(Miner, args):
	log.debug('initializing NVML...')
	nvmlInit()

	log.info('started with nVidia driver version = %s', 
	nvmlSystemGetDriverVersion())

	log.debug('obtaining device ...')
	nvml_device = nvmlDeviceGetHandleByIndex(0)

	log.debug('querying for ID information...')
	labels = {
		'gpu_uuid':		nvmlDeviceGetUUID(nvml_device) ,
		'pci_bus_id':	nvmlDeviceGetPciInfo(nvml_device).busId
		}
	log.debug('device is %s', labels['gpu_uuid'])

	REGISTRY.register(NVMLCollector.NVMLCollector(labels, nvml_device))
	REGISTRY.register(Miner.MinerCollector(labels, args.miner_host, args.miner_port))
	if args.collector_port:
		log.debug('starting http server on port %d', args.collector_port)
		start_http_server(args.collector_port)
		log.info('HTTP server started on port %d', args.collector_port)

	while True:
		if args.gateway:
			log.debug('pushing metrics to gateway at %s...', args.gateway)
			hostname = platform.node()
			push_to_gateway(args.gateway, job=hostname, registry=REGISTRY)
			log.debug('push complete.')

		time.sleep(args.update_period)


def getHostMetadata():
	try:
		req = urllib2.Request('http://rancher-metadata/2015-12-19/self/host')
		req.add_header('Accept', 'application/json')
		resp = urllib2.urlopen(req)
		metadata = json.loads(resp.read())
	except socket.error as e:
		log.info('not able to get metadata: %s', e)
		return None
	return metadata

def main():
	parser = _create_parser()
	args = parser.parse_args()
	logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

	Miner = importlib.import_module(args.miner_module, package=None)

	try:
		log.debug('initializing NVML...')
		nvmlInit()

		log.info('started with nVidia driver version = %s', nvmlSystemGetDriverVersion())

		log.debug('obtaining device ...')
		nvml_device = nvmlDeviceGetHandleByIndex(0)

		gpu_uuid = nvmlDeviceGetUUID(nvml_device)
		device_name = nvmlDeviceGetName(nvml_device)
		log.info('%s is a %s', gpu_uuid, device_name)

		gpu_uuid_short = gpu_uuid.split('-')[-1]

		metadata = getHostMetadata()

		key = "coolbits-%s"%gpu_uuid_short
		if key in metadata['labels']:
			coolbits = metadata['labels'][key].split(',')

			mW = int(coolbits[0])
			log.info('setting new power limit: %dmW', mW)
			nvmlDeviceSetPowerManagementLimit(nvml_device, mW)

		pid = os.fork()

		if ( pid == 0 ):
			log.info('collect as a child process %d'%os.getpid())
			collect(Miner, args)

		Miner.launch(args, metadata, gpu_uuid_short)

	except Exception as e:
		log.error('Exception thrown - %s', e, exc_info=True)
	finally:
		nvmlShutdown()
   

if __name__ == '__main__':
	main()
