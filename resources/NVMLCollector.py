import logging

from prometheus_client import CollectorRegistry, Gauge, Counter, push_to_gateway
from prometheus_client import start_http_server, core
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY

from pynvml import *

log = logging.getLogger('nvml-exporter')

class NVMLCollector(object):

	def __init__(self, labels, device):
		self.labels	= labels
		self.device	= device

		self.prefix		= 'nvml_'
		self.prefix_s	= 'NVML '

	def collect(self):
		try:
			log.debug('Querying for clocks information...')
			graphics_clock_mhz = nvmlDeviceGetClockInfo(self.device, NVML_CLOCK_GRAPHICS)
			metric = GaugeMetricFamily(self.prefix + 'clock_gpu_hz', self.prefix_s + "GPU clock", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), graphics_clock_mhz * 1000000)
			yield metric
			mem_clock_mhz = nvmlDeviceGetClockInfo(self.device, NVML_CLOCK_MEM)
			metric = GaugeMetricFamily(self.prefix + 'clock_mem_hz', self.prefix_s + "MEM clock", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), mem_clock_mhz * 1000000)
			yield metric

			log.debug('Querying for temperature information...')
			gpu_temperature_c = nvmlDeviceGetTemperature(self.device, NVML_TEMPERATURE_GPU)
			metric = GaugeMetricFamily(self.prefix + 'gpu_temperature_c', self.prefix_s + "GPU temperature", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), gpu_temperature_c)
			yield metric

			log.debug('Querying for fan information...')
			metric = GaugeMetricFamily(self.prefix + 'fan_speed_percent', self.prefix_s + "fan speed", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), nvmlDeviceGetFanSpeed(self.device))
			yield metric

			log.debug('Querying for power information...')
			power_usage_w = nvmlDeviceGetPowerUsage(self.device) / 1000.0
			metric = GaugeMetricFamily(self.prefix + 'power_draw_watt', self.prefix_s + "power draw", labels=self.labels.keys())
			metric.add_metric(self.labels.values(), power_usage_w)
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

			log.info('collected power:%.1fW temp:%dc gpu:%dMHz mem:%dMHz', power_usage_w, gpu_temperature_c, graphics_clock_mhz, mem_clock_mhz)
		except Exception as e:
			log.warning(e, exc_info=True)