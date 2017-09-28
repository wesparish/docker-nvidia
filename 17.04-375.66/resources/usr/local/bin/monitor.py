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
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY

from pynvml import *


log = logging.getLogger('prometheus-nvidia-exporter')

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

class NVMLCollector(object):

	def __init__(self, labels, device):
		self.labels	= labels
		self.device	= device

		self.prefix		= 'nvml_'
		self.prefix_s	= 'NVML '

	def collect(self):
		try:
			log.debug('Querying for clocks information...')
			metric = GaugeMetricFamily(self.prefix + 'clock_gpu_hz', self.prefix_s + "GPU clock", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), nvmlDeviceGetClockInfo(self.device, NVML_CLOCK_GRAPHICS) * 1000000)
			yield metric
			metric = GaugeMetricFamily(self.prefix + 'clock_mem_hz', self.prefix_s + "MEM clock", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), nvmlDeviceGetClockInfo(self.device, NVML_CLOCK_MEM) * 1000000)
			yield metric

			log.debug('Querying for temperature information...')
			metric = GaugeMetricFamily(self.prefix + 'gpu_temperature_c', self.prefix_s + "GPU temperature", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), nvmlDeviceGetTemperature(self.device, NVML_TEMPERATURE_GPU))
			yield metric

			log.debug('Querying for fan information...')
			metric = GaugeMetricFamily(self.prefix + 'fan_speed_percent', self.prefix_s + "fan speed", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), nvmlDeviceGetFanSpeed(self.device))
			yield metric

			log.debug('Querying for power information...')
			metric = GaugeMetricFamily(self.prefix + 'power_draw_watt', self.prefix_s + "power draw", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), nvmlDeviceGetPowerUsage(self.device) / 1000.0)
			yield metric
			metric = GaugeMetricFamily(self.prefix + 'power_state', self.prefix_s + "power state", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), nvmlDeviceGetPowerState(self.device))
			yield metric

			log.debug('Querying for memory information...')
			mem_info = nvmlDeviceGetMemoryInfo(self.device)
			metric = GaugeMetricFamily(self.prefix + 'memory_total_bytes', self.prefix_s + "total memory", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), mem_info.total)
			yield metric
			metric = GaugeMetricFamily(self.prefix + 'memory_used_bytes', self.prefix_s + "used memory", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), mem_info.used)
			yield metric
		except Exception as e:
			log.warning(e, exc_info=True)



class ClaymoreCollector(object):
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

	def __init__(self, labels, hostname, port):
		self.labels		= labels
		self.hostname	= hostname
		self.port		= port

		self.prefix		= 'claymore_'
		self.prefix_s	= 'Claymore '

	def getAPIStat(self):
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			log.debug('Connecting to claymore ...')
			s.connect((self.hostname, self.port))
			log.debug('Sending signing request to the server')
			s.sendall(json.dumps(self.CLAYMORE_API_CALL_GETSTAT))
			log.debug('Waiting for server response')
			response = s.recv(10 * 1024)
			log.debug('Parsing JSON response')
			stat = json.loads(response)
		except socket.error as e:
			log.info('Claymore not available: %s', e)
			return None
		finally:
			s.close()
		return stat['result']

	def collect(self):
		stat = self.getAPIStat()

		if ( not stat ):
			return

		try:
			#LABELS
			self.labels['version'] = stat[self.CLAYMORE_API_RESULT_VERSION]

			pools_s = stat[self.CLAYMORE_API_RESULT_POOLS].split(';', 2)
			self.labels['eth_pool_current'] = pools_s[0]
			# self.labels['dcr_pool_current'] = pools_s[1] if len(pools_s) >= 2 else None

			#COUNTERS
			metric = CounterMetricFamily(self.prefix + 'uptime_minutes', self.prefix_s + "uptime", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), float(stat[self.CLAYMORE_API_RESULT_UPTIME]))
			yield metric

			eth_shares_invalid, eth_pool_switches, dcr_shares_invalid, dcr_pool_switches = stat[self.CLAYMORE_API_RESULT_EVENTS].split(';', 4)
			metric = CounterMetricFamily(self.prefix + 'eth_shares_invalid', self.prefix_s + "ETH invalid shares", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), float(eth_shares_invalid))
			yield metric
			metric = CounterMetricFamily(self.prefix + 'eth_pool_switches', self.prefix_s + "ETH pool swithes", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), float(eth_pool_switches))
			yield metric
			# metric = CounterMetricFamily(self.prefix + 'dcr_shares_invalid', self.prefix_s + "DCR invalid shares", labels=self.labels.keys())
			# metric.add_metric(self.labels.values(), dcr_shares_invalid)
			# yield metric
			# metric = CounterMetricFamily(self.prefix + 'dcr_pool_switches', self.prefix_s + "DCR pool swithes", labels=self.labels.keys())
			# metric.add_metric(self.labels.values(), dcr_pool_switches)
			# yield metric

			eth_hashrate_total_mhs, eth_shares_accepted, eth_shares_rejected = stat[self.CLAYMORE_API_RESULT_ETH_SHARES_TOTAL].split(';', 3)
			metric = CounterMetricFamily(self.prefix + 'eth_shares_accepted', self.prefix_s + "ETH accepted shares", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), float(eth_shares_accepted))
			yield metric
			metric = CounterMetricFamily(self.prefix + 'eth_shares_rejected', self.prefix_s + "ETH rejected shares", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), float(eth_shares_rejected))
			yield metric

			#GAUGES
			metric = GaugeMetricFamily(self.prefix + 'eth_hashrate_total_mhs', self.prefix_s + "ETH total hashrate", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), float(eth_hashrate_total_mhs))
			yield metric
			gpu_temperature_c, fan_speed_percent = stat[self.CLAYMORE_API_RESULT_TEMP_FAN].split(';', 2)
			metric = GaugeMetricFamily(self.prefix + 'gpu_temperature_c', self.prefix_s + "GPU temperature", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), float(gpu_temperature_c))
			yield metric
			metric = GaugeMetricFamily(self.prefix + 'fan_speed_percent', self.prefix_s + "GPU fan speed", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), float(fan_speed_percent))
			yield metric

		except Exception as e:
			log.warning(e, exc_info=True)


def main():
	parser = _create_parser()
	args = parser.parse_args()
	logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

	try:
		log.debug('Initializing NVML...')
		nvmlInit()

		log.info('Started with nVidia driver version = %s', 
		nvmlSystemGetDriverVersion())

		log.debug('Obtaining device ...')
		nvml_device = nvmlDeviceGetHandleByIndex(0)

		log.debug('Querying for ID information...')
		labels = {
			'gpu_uuid':		nvmlDeviceGetUUID(nvml_device),
			'pci_bus_id':	nvmlDeviceGetPciInfo(nvml_device).busId
			}
		log.debug('Device is %s', labels['gpu_uuid'])

		REGISTRY.register(NVMLCollector(labels, nvml_device))
		REGISTRY.register(ClaymoreCollector(labels, args.claymore_host, args.claymore_port))

		if args.port:
			log.debug('Starting http server on port %d', args.port)
			start_http_server(args.port)
			log.info('HTTP server started on port %d', args.port)

		while True:
			if args.gateway:
				log.debug('Pushing metrics to gateway at %s...', args.gateway)
				hostname = platform.node()
				push_to_gateway(args.gateway, job=hostname, registry=REGISTRY)
				log.debug('Push complete.')

			time.sleep(args.update_period)

	except Exception as e:
		log.error('Exception thrown - %s', e, exc_info=True)
	finally:
		nvmlShutdown()
   

if __name__ == '__main__':
	main()
