#!/usr/bin/python

"""
Pushes nVidia GPU metrics to a Prometheus Push gateway for later collection.
"""

import argparse
import logging
import time
import platform

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from prometheus_client import start_http_server, core

from pynvml import *


log = logging.getLogger('nvidia-tool')


def _create_parser():
	parser = argparse.ArgumentParser(description='nVidia GPU Prometheus '

												 'Metrics Exporter')
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

	return parser


def main():
	parser = _create_parser()
	args = parser.parse_args()
	logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    
	registry = core.REGISTRY

	temperature_gpu = Gauge('gpu_temperature_gpu_c', "GPU temperature", ['gpu_uuid', 'pci_bus_id'], registry=registry)
	memory_total	= Gauge('gpu_memory_total_mb', "GPU total memory", ['gpu_uuid', 'pci_bus_id'], registry=registry)
	memory_used		= Gauge('gpu_memory_used_mb', "GPU used memory", ['gpu_uuid', 'pci_bus_id'], registry=registry)
	fan_speed       = Gauge('gpu_fan_speed_percent', "GPU fan speed", ['gpu_uuid', 'pci_bus_id'], registry=registry)
	power_draw      = Gauge('gpu_power_draw_watt', "GPU power draw", ['gpu_uuid', 'pci_bus_id'], registry=registry)
	clock_gpu       = Gauge('gpu_clock_gpu_hz', "GPU clock", ['gpu_uuid', 'pci_bus_id'], registry=registry)
	clock_mem       = Gauge('gpu_clock_mem_hz', "GPU memory clock", ['gpu_uuid', 'pci_bus_id'], registry=registry)
	power_state     = Gauge('gpu_power_state', "GPU power state", ['gpu_uuid', 'pci_bus_id'], registry=registry)


	iteration = 0

	try:
		log.debug('Initializing NVML...')
		nvmlInit()

		log.info('Started with nVidia driver version = %s', 
		nvmlSystemGetDriverVersion())

		device_count = nvmlDeviceGetCount()
		log.debug('%d devices found.', device_count)

		if args.port:
			log.debug('Starting http server on port %d', args.port)
			start_http_server(args.port)
			log.info('HTTP server started on port %d', args.port)

		while True:

			iteration += 1
			log.debug('Current iteration = %d', iteration)

			for i in range(device_count):
				log.debug('Analyzing device %d...', i)
				try:
					log.debug('Obtaining device %d...', i)
					device = nvmlDeviceGetHandleByIndex(i)
					log.debug('Device %d is %s', i, str(device))

					log.debug('Querying for ID information...')
					gpu_uuid	= nvmlDeviceGetUUID(device)
					pci			= nvmlDeviceGetPciInfo(device)
					pci_bus_id	= pci.busId

					log.debug('Querying for clocks information...')
					clock_gpu.labels(gpu_uuid=gpu_uuid, pci_bus_id=pci_bus_id).set(nvmlDeviceGetClockInfo(device, NVML_CLOCK_GRAPHICS))
					clock_mem.labels(gpu_uuid=gpu_uuid, pci_bus_id=pci_bus_id).set(nvmlDeviceGetClockInfo(device, NVML_CLOCK_MEM))

					log.debug('Querying for temperature information...')
					temperature_gpu.labels(gpu_uuid=gpu_uuid, pci_bus_id=pci_bus_id).set(nvmlDeviceGetTemperature(device, NVML_TEMPERATURE_GPU))

					log.debug('Querying for fan information...')
					fan_speed.labels(gpu_uuid=gpu_uuid, pci_bus_id=pci_bus_id).set(nvmlDeviceGetFanSpeed(device))

					log.debug('Querying for power information...')
					power_draw.labels(gpu_uuid=gpu_uuid, pci_bus_id=pci_bus_id).set(nvmlDeviceGetPowerUsage(device) / 1000.0)
					power_state.labels(gpu_uuid=gpu_uuid, pci_bus_id=pci_bus_id).set(nvmlDeviceGetPowerState(device))

					log.debug('Querying for memory information...')
					mem_info = nvmlDeviceGetMemoryInfo(device)
					memory_total.labels(gpu_uuid=gpu_uuid, pci_bus_id=pci_bus_id).set(mem_info.total / 1024.0 / 1024.0)
					memory_used.labels(gpu_uuid=gpu_uuid, pci_bus_id=pci_bus_id).set(mem_info.used / 1024.0 / 1024.0)

				except Exception as e:
					log.warning(e, exc_info=True)

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
