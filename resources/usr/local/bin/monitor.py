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

import MinerCollector

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

	parser.add_argument('-mh', '--miner-host',
						help='miner API hostname',
						default="localhost")

	parser.add_argument('-mp', '--miner-port',
						help='miner API tcp port',
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
		REGISTRY.register(MinerCollector.MinerCollector(labels, args.miner_host, args.miner_port))

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
