# defusedxml
#
# Copyright (c) 2013 by Christian Heimes <christian@python.org>
# Licensed to PSF under a Contributor Agreement.
# See https://www.python.org/psf/license for licensing details.
"""Defuse XML bomb denial of service vulnerabilities
"""
from __future__ import print_function, absolute_import

from .common import (
    DefusedXmlException,
    DTDForbidden,
    EntitiesForbidden,
    ExternalReferenceForbidden,
    NotSupportedError,
)


# NOTA (IOF Assistent): d'aquest paquet vendoritzat només s'utilitza
# defusedxml.ElementTree (per parsejar el feed ATOM del Cadastre de forma
# segura). S'ha eliminat la funció `defuse_stdlib()` de la font original
# perquè importava mòduls (xmlrpc, pulldom, minidom, sax, expatbuilder,
# expatreader, cElementTree) que aquest plugin no fa servir mai i que
# l'escàner de seguretat de plugins.qgis.org marcava com a crítics per
# patrons de parsing XML "insegur" (fals positiu: és precisament el codi
# amb què defusedxml neutralitza aquests patrons). Aquests mòduls també
# s'han eliminat d'aquesta carpeta; vegeu el paquet oficial defusedxml
# si en necessiteu la funcionalitat completa.

__version__ = "0.7.1"

__all__ = [
    "DefusedXmlException",
    "DTDForbidden",
    "EntitiesForbidden",
    "ExternalReferenceForbidden",
    "NotSupportedError",
]
