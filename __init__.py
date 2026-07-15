# -*- coding: utf-8 -*-
def classFactory(iface):
    try:
        from .iof_exporter import IOFExporter
        return IOFExporter(iface)
    except Exception as e:
        from qgis.core import QgsMessageLog, Qgis
        QgsMessageLog.logMessage(
            f"IOF Exporter — error de càrrega: {e}",
            "IOF Exporter",
            level=Qgis.MessageLevel.Critical
        )
        raise
