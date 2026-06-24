"""
Bus SPI dùng chung cho MCP3008 — line sensor (CH0-5) + IR pallet (CH6-7).
Một lock tránh tranh chấp khi Motion và Lift đọc đồng thời.
"""

import threading
import logging

try:
    from gpiozero import MCP3008 as _MCP3008
    from gpiozero import Device
    Device.ensure_pin_factory()
except Exception:
    _MCP3008 = None

import config

logger = logging.getLogger(__name__)

_bus: "Mcp3008Bus | None" = None
_bus_lock = threading.Lock()


class Mcp3008Bus:
    """Đọc analog MCP3008 (0.0-1.0) qua SPI với lock."""

    def __init__(self):
        self._lock = threading.Lock()
        self._channels: dict[int, object] = {}
        self.available = False
        if _MCP3008 is None:
            logger.warning("gpiozero.MCP3008 không khả dụng")
            return
        try:
            self.available = True
            logger.info(
                "MCP3008 bus sẵn sàng (SPI port=%d CS=%d)",
                config.MCP3008_SPI_PORT, config.MCP3008_CS,
            )
        except Exception as e:
            logger.warning("MCP3008 bus không khả dụng (%s)", e)
            self.available = False

    def _get_channel(self, channel: int):
        if channel not in self._channels:
            self._channels[channel] = _MCP3008(
                channel=channel,
                port=config.MCP3008_SPI_PORT,
                device=config.MCP3008_CS,
            )
        return self._channels[channel]

    def read(self, channel: int) -> float:
        """Đọc 1 kênh (0.0-1.0). Trả 1.0 nếu bus không khả dụng."""
        if not self.available:
            return 1.0
        with self._lock:
            try:
                return self._get_channel(channel).value
            except Exception as e:
                logger.warning("Lỗi đọc MCP3008 CH%d: %s", channel, e)
                return 1.0

    def read_many(self, channels: list[int]) -> list[float]:
        """Đọc nhiều kênh trong một lần khóa."""
        if not self.available:
            return [1.0] * len(channels)
        with self._lock:
            values = []
            for ch in channels:
                try:
                    values.append(self._get_channel(ch).value)
                except Exception as e:
                    logger.warning("Lỗi đọc MCP3008 CH%d: %s", ch, e)
                    values.append(1.0)
            return values

    def read_adc(self, channel: int) -> int:
        """Đọc giá trị ADC 0-1023."""
        return int(round(self.read(channel) * 1023))

    def cleanup(self):
        with self._lock:
            for ch in self._channels.values():
                try:
                    ch.close()
                except Exception:
                    pass
            self._channels.clear()
            self.available = False


def get_mcp3008_bus() -> Mcp3008Bus:
    """Singleton — Motion và Lift dùng chung một bus."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = Mcp3008Bus()
    return _bus


def reset_mcp3008_bus():
    """Đóng bus (test / shutdown)."""
    global _bus
    with _bus_lock:
        if _bus is not None:
            _bus.cleanup()
            _bus = None
