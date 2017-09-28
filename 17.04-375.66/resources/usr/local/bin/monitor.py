#!/usr/bin/python

"""
Pushes nVidia GPU metrics to a Prometheus Push gateway for later collection.
"""

import argparse
import logging
import time
import platform

import socket
import sys
import json

from prometheus_client import CollectorRegistry, Gauge, Counter, push_to_gateway
from prometheus_client import start_http_server, core

from pynvml import *


log = logging.getLogger('nvidia-tool')

CLAYMORE_API_CALL_GETSTAT		= {'id':0, 'jsonrpc':"2.0", 'method':"miner_getstat1"}

# [u'9.8 - ETH', u'949', u'26642;328;0', u'26642', u'0;0;0', u'off', u'64;48', u'eu1.ethermine.org:4444', u'0;0;0;0']
CLAYMORE_API_RESULT_VERSION				= 0
CLAYMORE_API_RESULT_UPTIME				= 1
CLAYMORE_API_RESULT_ETH_SHARES_TOTAL	= 2
CLAYMORE_API_RESULT_ETH_SHARES_ONE		= 3
CLAYMORE_API_RESULT_DCH_SHARES_TOTAL	= 4
CLAYMORE_API_RESULT_DCH_SHARES_ONE		= 5
CLAYMORE_API_RESULT_TEMP_FAN			= 6
CLAYMORE_API_RESULT_POOLS				= 7
CLAYMORE_API_RESULT_EVENTS				= 8

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

	parser.add_argument('-p', '--port',
						help='If non-zero, port to run the http server',
						type=int,
						default=0)

	parser.add_argument('-ch', '--claymore-host',
						help='Claymore API hostname',
						default="localhost")

	parser.add_argument('-cp', '--claymore-port',
						help='Claymore API tcp port',
						type=int,
						default=3333)



	return parser

def getNVMLData(args, nvml_device):
	data = {}
	try:
		log.debug('Querying for ID information...')
		data['gpu_uuid'] = nvmlDeviceGetUUID(nvml_device)
		data['pci_bus_id'] = nvmlDeviceGetPciInfo(nvml_device).busId
		log.debug('Device is %s', data['gpu_uuid'])

		log.debug('Querying for clocks information...')
		data['clock_gpu_hz']	= nvmlDeviceGetClockInfo(nvml_device, NVML_CLOCK_GRAPHICS) * 1000000
		data['clock_mem_hz']	= nvmlDeviceGetClockInfo(nvml_device, NVML_CLOCK_MEM) * 1000000

		log.debug('Querying for temperature information...')
		data['gpu_temperature_c']	= nvmlDeviceGetTemperature(nvml_device, NVML_TEMPERATURE_GPU)

		log.debug('Querying for fan information...')
		data['fan_speed_percent']	= nvmlDeviceGetFanSpeed(nvml_device)

		log.debug('Querying for power information...')
		data['power_draw_watt']	= nvmlDeviceGetPowerUsage(nvml_device) / 1000.0
		data['power_state'] 	= nvmlDeviceGetPowerState(nvml_device)

		log.debug('Querying for memory information...')
		mem_info = nvmlDeviceGetMemoryInfo(nvml_device)
		data['memory_total_bytes']	= mem_info.total
		data['memory_used_bytes']	= mem_info.used

	except Exception as e:
		log.warning(e, exc_info=True)

	return data

def getClaymoreAPIData(args):
	data = {}

	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	response_data = None
	try:
		log.debug('Connecting to claymore ...')
		s.connect((args.claymore_host, args.claymore_port))
		log.debug('Sending signing request to the server')
		s.sendall(json.dumps(CLAYMORE_API_CALL_GETSTAT))
		log.debug('Waiting for server response')
		response_data = s.recv(10 * 1024)
		log.debug('Got server response')
	except socket.error as e:
		log.debug('Claymore not available: %s', e)
	finally:
		s.close()

	if ( not response_data ):
		return None

	try:
		log.debug('Parsing JSON response')
		response = json.loads(response_data)

		data['version'] = response['result'][CLAYMORE_API_RESULT_VERSION]

		pools_s = response['result'][CLAYMORE_API_RESULT_POOLS].split(';', 2)
		data['eth_pool_current'] = pools_s[0]
		data['dcr_pool_current'] = pools_s[1] if len(pools_s) >= 2 else None

		data['uptime_minutes'] = response['result'][CLAYMORE_API_RESULT_UPTIME]

		eth_hashrate_total_mhs, eth_shares_accepted, eth_shares_rejected = response['result'][CLAYMORE_API_RESULT_ETH_SHARES_TOTAL].split(';', 3)
		data['eth_hashrate_total_mhs']	= eth_hashrate_total_mhs
		data['eth_shares_accepted']		= eth_shares_accepted
		data['eth_shares_rejected']		= eth_shares_rejected

		gpu_temperature_c, fan_speed_percent = response['result'][CLAYMORE_API_RESULT_TEMP_FAN].split(';', 2)
		data['gpu_temperature_c']		= gpu_temperature_c
		data['fan_speed_percent']	= fan_speed_percent

		eth_shares_invalid, eth_pool_switches, dcr_shares_invalid, dcr_pool_switches = response['result'][CLAYMORE_API_RESULT_EVENTS].split(';', 4)
		data['eth_shares_invalid']		= eth_shares_invalid
		data['eth_pool_switches']		= eth_pool_switches
		data['dcr_shares_invalid']		= dcr_shares_invalid
		data['dcr_pool_switches']		= dcr_pool_switches

	except Exception as e:
		print e

	return data

def main():
	parser = _create_parser()
	args = parser.parse_args()
	logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    
	registry = core.REGISTRY

	nvml_sensors = {
		'gpu_temperature_c':	Gauge('nvml_gpu_temperature_c',		"NVML GPU temperature",	['gpu_uuid', 'pci_bus_id'],	registry=registry),
		'memory_total_bytes':	Gauge('nvml_memory_total_bytes',	"NVML total memory",	['gpu_uuid', 'pci_bus_id'],	registry=registry),
		'memory_used_bytes':	Gauge('nvml_memory_used_bytes',		"NVML used memory",		['gpu_uuid', 'pci_bus_id'],	registry=registry),
		'fan_speed_percent':	Gauge('nvml_fan_speed_percent',		"NVML fan speed",		['gpu_uuid', 'pci_bus_id'],	registry=registry),
		'power_draw_watt':		Gauge('nvml_power_draw_watt',		"NVML power draw",		['gpu_uuid', 'pci_bus_id'],	registry=registry),
		'clock_gpu_hz':			Gauge('nvml_clock_gpu_hz',			"NVML GPU clock",		['gpu_uuid', 'pci_bus_id'],	registry=registry),
		'clock_mem_hz':			Gauge('nvml_clock_mem_hz',			"NVML MEM clock",		['gpu_uuid', 'pci_bus_id'],	registry=registry),
		'power_state':			Gauge('nvml_power_state',			"NVML power state",		['gpu_uuid', 'pci_bus_id'],	registry=registry)
		}

	claymore_sensors = {
		'uptime_minutes':			Gauge('claymore_uptime_minutes',			"Claymore uptime",				['gpu_uuid', 'pci_bus_id', 'claymore_version', 'eth_pool'],	registry=registry),
		'eth_shares_accepted':		Gauge('claymore_eth_shares_accepted',		"Claymore ETH accepted shares",	['gpu_uuid', 'pci_bus_id', 'claymore_version', 'eth_pool'],	registry=registry),
		'eth_shares_rejected':		Gauge('claymore_eth_shares_rejected',		"Claymore ETH rejected shares",	['gpu_uuid', 'pci_bus_id', 'claymore_version', 'eth_pool'],	registry=registry),
		'eth_shares_invalid':		Gauge('claymore_eth_shares_invalid',		"Claymore ETH invalid shares",	['gpu_uuid', 'pci_bus_id', 'claymore_version', 'eth_pool'],	registry=registry),
		'eth_pool_switches':		Gauge('claymore_eth_pool_switches',		"Claymore ETH pool swithes",	['gpu_uuid', 'pci_bus_id', 'claymore_version', 'eth_pool'],	registry=registry),
		'eth_hashrate_total_mhs':	Gauge('claymore_eth_hashrate_total_mhs',	"Claymore ETH total hashrate",	['gpu_uuid', 'pci_bus_id', 'claymore_version', 'eth_pool'],	registry=registry),
		'gpu_temperature_c':		Gauge('claymore_gpu_temperature_c',			"Claymore GPU temperature",		['gpu_uuid', 'pci_bus_id', 'claymore_version', 'eth_pool'],	registry=registry),
		'fan_speed_percent':		Gauge('claymore_fan_speed_percent',			"Claymore GPU fan speed",		['gpu_uuid', 'pci_bus_id', 'claymore_version', 'eth_pool'],	registry=registry)
		}

	try:
		log.debug('Initializing NVML...')
		nvmlInit()

		log.info('Started with nVidia driver version = %s', 
		nvmlSystemGetDriverVersion())

		log.debug('Obtaining device ...')
		nvml_device = nvmlDeviceGetHandleByIndex(0)

		# device_count = nvmlDeviceGetCount()
		# log.debug('%d devices found.', device_count)

		if args.port:
			log.debug('Starting http server on port %d', args.port)
			start_http_server(args.port)
			log.info('HTTP server started on port %d', args.port)

		while True:
			nvml_data		= getNVMLData(args, nvml_device)
			for key in nvml_sensors:
				nvml_sensors[key].labels(gpu_uuid=nvml_data['gpu_uuid'], pci_bus_id=nvml_data['pci_bus_id']).set(nvml_data[key])

			claymore_data	= getClaymoreAPIData(args)
			if (claymore_data):
				for key in claymore_sensors:
					claymore_sensors[key].labels(gpu_uuid=nvml_data['gpu_uuid'], pci_bus_id=nvml_data['pci_bus_id'], claymore_version=claymore_data['version'], eth_pool=claymore_data['eth_pool_current']).set(claymore_data[key])

			if args.gateway:
				log.debug('Pushing metrics to gateway at %s...', args.gateway)
				hostname = platform.node()
				push_to_gateway(args.gateway, job=hostname, registry=core.REGISTRY)
				log.debug('Push complete.')

			time.sleep(args.update_period)

	except Exception as e:
		log.error('Exception thrown - %s', e, exc_info=True)
	finally:
		nvmlShutdown()
   

if __name__ == '__main__':
	main()
