import sys
import os
import json
import requests
import threading
import csv
import queue
import re
import shutil
from datetime import datetime
from collections import deque

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget, 
                             QTableWidgetItem, QTableView, QHeaderView, QFormLayout, QStyledItemDelegate,
                             QMessageBox, QTabWidget, QListWidget, QAbstractItemView, QCheckBox, 
                             QFileDialog, QSpinBox, QStyle, QDialog, QRadioButton, QMenu, QInputDialog,
                             QScrollArea, QShortcut, QStyleOptionViewItem)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QObject, QRectF, QEvent, QTimer, QAbstractTableModel, QModelIndex
from PyQt5.QtGui import QTextDocument, QColor, QKeySequence
import ctypes

# Dynamic loading of the FAAD2 C++ library based on architecture (32-bit or 64-bit)
try:
    is_64bits = (ctypes.sizeof(ctypes.c_void_p) == 8)
    
    if sys.platform.startswith('win'):
        # Automatic selection of the DLL, 32-bit or 64-bit
        _lib_name = "aac_uecp_x64.dll" if is_64bits else "aac_uecp_x86.dll"
        _lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _lib_name)
        # Fall back to the standard name if the specific file with the suffix does not exist
        if not os.path.exists(_lib_path):
            _lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aac_uecp.dll")
    else:
        _lib_name = "libaac_uecp_x64.so" if is_64bits else "libaac_uecp_x86.so"
        _lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _lib_name)
        if not os.path.exists(_lib_path):
            _lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libaac_uecp.so")
            
    aac_lib = ctypes.CDLL(_lib_path)
    
    # C++ to Python callback signature (UECP data extracted by FAAD2)
    UECP_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t)
    
    aac_lib.aac_decoder_init.argtypes = [UECP_CALLBACK]
    aac_lib.aac_decoder_init.restype = ctypes.c_void_p
    
    aac_lib.aac_decoder_feed.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
    aac_lib.aac_decoder_feed.restype = None
    
    aac_lib.aac_decoder_close.argtypes = [ctypes.c_void_p]
    aac_lib.aac_decoder_close.restype = None
except Exception as e:
    aac_lib = None
    print(f"The AAC Decoder library was not found or failed to load.\n\nError details:\n{e}")

# Multi-stream synchronization lock for the AAC DLL
_aac_feed_lock = threading.Lock()

# --- Default Services Data ---
DEFAULT_SERVICES = [
    {
        "name": "ARD (Germany) - BR [Astra 19.2\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:A:28A0:40F:1:C00000:0:0:0",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "aac",
        "pid": "101",
        "ow_streams": [
            {
                "name": "Bayern 1",
                "ref": "1:0:A:28A0:40F:1:C00000:0:0:0",
                "uecp_source": "aac",
                "pid": "101"
            },
            {
                "name": "Bayern 2",
                "ref": "1:0:A:28A1:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "111"
            },
            {
                "name": "Bayern 3",
                "ref": "1:0:A:28A2:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "121"
            },
            {
                "name": "BR Heimat",
                "ref": "1:0:A:28A8:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "181"
            },
            {
                "name": "BR Klassik",
                "ref": "1:0:A:28A3:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "131"
            },
            {
                "name": "BR Schlager",
                "ref": "1:0:A:28A6:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "161"
            },
            {
                "name": "BR24",
                "ref": "1:0:A:28A4:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "141"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "ARD (Germany) - hr [Astra 19.2\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:A:28E5:425:1:C00000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "12",
        "url_pids": "all",
        "uecp_source": "aac",
        "pid": "741",
        "ow_streams": [
            {
                "name": "DASDING vom hr",
                "ref": "1:0:A:28E5:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "741"
            },
            {
                "name": "hr INFO",
                "ref": "1:0:A:28E6:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "751"
            },
            {
                "name": "hr1",
                "ref": "1:0:A:28E1:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "701"
            },
            {
                "name": "hr2",
                "ref": "1:0:A:28E2:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "711"
            },
            {
                "name": "hr3",
                "ref": "1:0:A:28E3:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "721"
            },
            {
                "name": "hr4",
                "ref": "1:0:A:28E4:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "731"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "ARD (Germany) - MDR [Astra 19.2\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:A:28F0:425:1:C00000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "aac",
        "pid": "861",
        "ow_streams": [
            {
                "name": "MDR Aktuell",
                "ref": "1:0:A:28F0:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "861"
            },
            {
                "name": "MDR JUMP",
                "ref": "1:0:A:28EE:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "841"
            },
            {
                "name": "MDR Klassik",
                "ref": "1:0:A:28F1:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "871"
            },
            {
                "name": "MDR Kultur",
                "ref": "1:0:A:28ED:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "831"
            },
            {
                "name": "MDR Sachsen",
                "ref": "1:0:A:28EA:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "801"
            },
            {
                "name": "MDR Sachsen-Anhalt",
                "ref": "1:0:A:28EB:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "811"
            },
            {
                "name": "MDR Sputnik",
                "ref": "1:0:A:28EF:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "851"
            },
            {
                "name": "MDR Th\u00fcringen",
                "ref": "1:0:A:28EC:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "821"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "ARD (Germany) - NDR [Astra 19.2\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:A:28B2:40F:1:C00000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "aac",
        "pid": "261",
        "ow_streams": [
            {
                "name": "NDR 1 MV SN",
                "ref": "1:0:A:28B2:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "261"
            },
            {
                "name": "NDR 1 Nieders. HAN",
                "ref": "1:0:A:28B3:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "271"
            },
            {
                "name": "NDR 1 Welle Nord",
                "ref": "1:0:A:28B1:40F:1:C00000:0:0:0",
                "uecp_source": "aac",
                "pid": "251"
            },
            {
                "name": "NDR 2 NDS",
                "ref": "1:0:A:28AC:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "201"
            },
            {
                "name": "NDR 90,3",
                "ref": "1:0:A:28B0:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "241"
            },
            {
                "name": "NDR Blue",
                "ref": "1:0:A:28B5:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "291"
            },
            {
                "name": "NDR Info NDS",
                "ref": "1:0:A:28AE:40F:1:C00000:0:0:0",
                "uecp_source": "aac",
                "pid": "221"
            },
            {
                "name": "NDR Info Spezial",
                "ref": "1:0:A:28B4:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "281"
            },
            {
                "name": "NDR Kultur",
                "ref": "1:0:A:28AD:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "213"
            },
            {
                "name": "NDR Schlager",
                "ref": "1:0:A:28B6:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "291"
            },
            {
                "name": "N-JOY",
                "ref": "1:0:A:28AF:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "231"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "ARD (Germany) - Radio Bremen [Astra 19.2\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:A:28BA:40F:1:C00000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "aac",
        "pid": "301",
        "ow_streams": [
            {
                "name": "Bremen Eins",
                "ref": "1:0:A:28BA:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "301"
            },
            {
                "name": "Bremen NEXT",
                "ref": "1:0:A:28BD:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "331"
            },
            {
                "name": "Bremen Vier",
                "ref": "1:0:A:28BC:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "321"
            },
            {
                "name": "Bremen Zwei",
                "ref": "1:0:A:28BB:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "311"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "ARD (Germany) - rbb [Astra 19.2\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:A:28F4:425:1:C00000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "aac",
        "pid": "901",
        "ow_streams": [
            {
                "name": "rbb24 Inforadio",
                "ref": "1:0:A:28F4:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "901"
            },
            {
                "name": "rbb radioeins",
                "ref": "1:0:A:28F8:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "941"
            },
            {
                "name": "rbb radio3",
                "ref": "1:0:A:28F5:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "911"
            },
            {
                "name": "rbb Fritz",
                "ref": "1:0:A:28F9:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "951"
            },
            {
                "name": "rbb Antenne Brandenburg",
                "ref": "1:0:A:28F6:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "921"
            },
            {
                "name": "rbb 88.8",
                "ref": "1:0:A:28F7:425:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "931"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "ARD (Germany) - SR [Astra 19.2\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:A:28C0:40F:1:C00000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "aac",
        "pid": "401",
        "ow_streams": [
            {
                "name": "SR 1 Europawelle",
                "ref": "1:0:A:28C0:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "401"
            },
            {
                "name": "SR 3 Saarlandwelle",
                "ref": "1:0:A:28C2:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "421"
            },
            {
                "name": "SR Kultur",
                "ref": "1:0:A:28C1:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "411"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "ARD (Germany) - SWR [Astra 19.2\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:A:28CE:40F:1:C00000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "aac",
        "pid": "561",
        "ow_streams": [
            {
                "name": "DASDING vom SWR",
                "ref": "1:0:A:28CE:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "561"
            },
            {
                "name": "SWR Aktuell",
                "ref": "1:0:A:28CF:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "571"
            },
            {
                "name": "SWR Kultur",
                "ref": "1:0:A:28CA:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "521"
            },
            {
                "name": "SWR1 BW",
                "ref": "1:0:A:28C8:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "501"
            },
            {
                "name": "SWR1 RLP",
                "ref": "1:0:A:28C9:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "511"
            },
            {
                "name": "SWR3",
                "ref": "1:0:A:28CB:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "531"
            },
            {
                "name": "SWR4 MZ",
                "ref": "1:0:A:28CD:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "551"
            },
            {
                "name": "SWR4 S",
                "ref": "1:0:A:28CC:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "541"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "ARD (Germany) - WDR [Astra 19.2\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:A:28D3:40F:1:C00000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "aac",
        "pid": "601",
        "ow_streams": [
            {
                "name": "WDR 1LIVE",
                "ref": "1:0:A:28D3:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "601"
            },
            {
                "name": "WDR 1LIVE diGGi",
                "ref": "1:0:A:28D9:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "661"
            },
            {
                "name": "WDR 2",
                "ref": "1:0:A:28D4:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "611"
            },
            {
                "name": "WDR 3",
                "ref": "1:0:A:28D5:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "621"
            },
            {
                "name": "WDR 4",
                "ref": "1:0:A:28D6:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "631"
            },
            {
                "name": "WDR 5",
                "ref": "1:0:A:28D7:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "641"
            },
            {
                "name": "WDR Cosmo",
                "ref": "1:0:A:28D8:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "651"
            },
            {
                "name": "WDR Die Maus",
                "ref": "1:0:A:28DA:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "671"
            },
            {
                "name": "WDR Event",
                "ref": "1:0:A:28DB:40F:1:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "681"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "DATA NRJGROUP [Eutelsat 5\u00b0W]",
        "src": 1,
        "freq": "11461",
        "pol": "h",
        "sr": "5780",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "pid": "161",
        "address_book": {
            "0": "[SYSTEM]",
            "0/1": "NRJ",
            "0/2": "Ch\u00e9rie FM",
            "0/3": "Rire & Chansons",
            "0/4": "Nostalgie",
            "31/5": "NRJ Lyon",
            "402/5": "NRJ L\u00e9man"
        },
        "psn_book": {}
    },
    {
        "name": "Deutschlandfunk [Astra 19.2\u00b0E]",
        "stream_type": "minisatip",
        "ow_ref": "",
        "src": 1,
        "freq": "11361",
        "pol": "h",
        "sr": "22000",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "8psk",
        "fec_en": True,
        "fec": "23",
        "url_pids": "all",
        "uecp_source": "mp2",
        "pid": "6901 / 6911 / 6921 / 6931",
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "Fun Radio (France) [Eutelsat 5\u00b0W]",
        "src": 1,
        "freq": "11461",
        "pol": "h",
        "sr": "5780",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "pid": "532",
        "address_book": {
            "0/15": "Fun Radio"
        },
        "psn_book": {
            "15": "Fun Radio"
        }
    },
    {
        "name": "German Stations - 12148H [Astra 19.2\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:A:AA:7:85:C00000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "12",
        "url_pids": "all",
        "uecp_source": "aac",
        "pid": "352",
        "ow_streams": [
            {
                "name": "Antenne Bayern",
                "ref": "1:0:A:AA:7:85:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "352"
            },
            {
                "name": "Oldie Antenne",
                "ref": "1:0:A:B4:7:85:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "368"
            },
            {
                "name": "Rock Antenne",
                "ref": "1:0:A:A0:7:85:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "304"
            },
            {
                "name": "Sunshine Live",
                "ref": "1:0:2:A9:7:85:C00000:0:0:0:",
                "uecp_source": "aac",
                "pid": "336"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "Lagard\u00e8re Group (France) [Eutelsat 5\u00b0W]",
        "src": 1,
        "freq": "11455",
        "pol": "h",
        "sr": "2550",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "pid": "471",
        "address_book": {
            "960": "RFM",
            "961": "Europe 2",
            "962": "Europe 1"
        },
        "psn_book": {}
    },
    {
        "name": "RTL (France) [Eutelsat 5\u00b0W]",
        "src": 1,
        "freq": "11455",
        "pol": "h",
        "sr": "2550",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "pid": "512",
        "address_book": {
            "563": "RTL"
        },
        "psn_book": {}
    },
    {
        "name": "RTL2 (France) [Eutelsat 5\u00b0W]",
        "src": 1,
        "freq": "11461",
        "pol": "h",
        "sr": "5780",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "pid": "522",
        "address_book": {},
        "psn_book": {
            "13": "RTL2"
        }
    },
    {
        "name": "RTP (Portugal) [Hispasat 30\u00b0W]",
        "stream_type": "minisatip",
        "ow_ref": "",
        "src": 1,
        "freq": "12519",
        "pol": "v",
        "sr": "1480",
        "msys": "dvbs",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "pid",
        "pid": "101",
        "ow_streams": [
            {
                "name": "RTP Portugal [Hispasat 30\u00b0W]",
                "ref": "",
                "uecp_source": "pid",
                "pid": "101"
            }
        ],
        "address_book": {},
        "psn_book": {
            "1": "RTP Antena 1",
            "2": "RTP Antena 2",
            "3": "RTP Antena 3",
            "4": "RTP Africa"
        }
    },
    {
        "name": "Slovakia - RDS SAT [Astra 23.5\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:2:1338:CA2:3:EB0000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "12",
        "url_pids": "all",
        "uecp_source": "pid",
        "pid": "5830",
        "ow_streams": [
            {
                "name": "SAT RDS [Astra 23.5\u00b0E]",
                "ref": "1:0:2:1338:CA2:3:EB0000:0:0:0:",
                "uecp_source": "pid",
                "pid": "5830"
            }
        ],
        "address_book": {
            "805/9": "Radio Rock",
            "341/21": "Fun Radio",
            "800/18": "Europa 2",
            "800/23": "Radio Vlna",
            "786/7": "Radio Melody",
            "769/2": "STVR Radio Slovensko",
            "804/5": "Radio Lumen",
            "0": "[SYSTEM]",
            "768/4": "STVR Radio Devin",
            "770/3": "STVR Radio Regina",
            "774/6": "STVR Radio_FM"
        },
        "psn_book": {}
    },
    {
        "name": "SRG SSR - Radio RTR [Hotbird 13.0\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:2:434A:300C:13E:820000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "mp2",
        "pid": "216",
        "ow_streams": [
            {
                "name": "SRG SSR - Radio RTR [Hotbird 13.0\u00b0E]",
                "ref": "1:0:2:434A:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "216"
            }
        ],
        "address_book": {
            "0": "Radio RTR"
        },
        "psn_book": {},
        "pid_book": {
            "216": "Radio RTR"
        }
    },
    {
        "name": "SRG SSR - RSI [Hotbird 13.0\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:2:4350:300C:13E:820000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "mp2",
        "pid": "222",
        "ow_streams": [
            {
                "name": "RSI Rete Due",
                "ref": "1:0:2:4350:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "222"
            },
            {
                "name": "RSI Rete Tre",
                "ref": "1:0:2:4351:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "223"
            },
            {
                "name": "RSI Rete Uno",
                "ref": "1:0:2:434F:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "221"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "SRG SSR - RTS [Hotbird 13.0\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:2:434D:300C:13E:820000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "mp2",
        "pid": "219",
        "ow_streams": [
            {
                "name": "RTS Couleur 3",
                "ref": "1:0:2:434D:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "219"
            },
            {
                "name": "RTS Espace 2",
                "ref": "1:0:2:434C:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "218"
            },
            {
                "name": "RTS Option Musique",
                "ref": "1:0:2:434E:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "220"
            },
            {
                "name": "RTS Premi\u00e8re",
                "ref": "1:0:2:434B:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "217"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "SRG SSR - SRF [Hotbird 13.0\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:2:4345:300C:13E:820000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "mp2",
        "pid": "211",
        "ow_streams": [
            {
                "name": "SRF 1",
                "ref": "1:0:2:4345:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "211"
            },
            {
                "name": "SRF 1 AG SO",
                "ref": "1:0:2:4358:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "230"
            },
            {
                "name": "SRF 1 BE FR VS",
                "ref": "1:0:2:435A:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "232"
            },
            {
                "name": "SRF 1 BS",
                "ref": "1:0:2:4359:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "231"
            },
            {
                "name": "SRF 1 GR",
                "ref": "1:0:2:435E:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "236"
            },
            {
                "name": "SRF 1 LU",
                "ref": "1:0:2:435B:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "233"
            },
            {
                "name": "SRF 1 SG",
                "ref": "1:0:2:435C:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "234"
            },
            {
                "name": "SRF 1 ZH SH",
                "ref": "1:0:2:435D:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "235"
            },
            {
                "name": "SRF 2 Kultur",
                "ref": "1:0:2:4346:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "212"
            },
            {
                "name": "SRF 3",
                "ref": "1:0:2:4347:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "213"
            },
            {
                "name": "SRF 4 News",
                "ref": "1:0:2:4355:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "227"
            },
            {
                "name": "SRF Musikwelle",
                "ref": "1:0:2:4349:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "215"
            },
            {
                "name": "SRF Virus",
                "ref": "1:0:2:4348:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "214"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "SRG SSR - Thematic stations [Hotbird 13.0\u00b0E]",
        "stream_type": "openwebif",
        "ow_ref": "1:0:2:4352:300C:13E:820000:0:0:0:",
        "src": 1,
        "freq": "",
        "pol": "h",
        "sr": "",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "uecp_source": "mp2",
        "pid": "224",
        "ow_streams": [
            {
                "name": "Swiss Classic",
                "ref": "1:0:2:4352:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "224"
            },
            {
                "name": "Swiss Classica",
                "ref": "1:0:2:435F:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "237"
            },
            {
                "name": "Swiss Classique",
                "ref": "1:0:2:4357:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "229"
            },
            {
                "name": "Swiss Jazz",
                "ref": "1:0:2:4354:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "226"
            },
            {
                "name": "Swiss Pop",
                "ref": "1:0:2:4353:300C:13E:820000:0:0:0:",
                "uecp_source": "mp2",
                "pid": "225"
            }
        ],
        "address_book": {},
        "psn_book": {}
    },
    {
        "name": "TDF-RDS1 [Eutelsat 5\u00b0W]",
        "src": 1,
        "freq": "11480",
        "pol": "h",
        "sr": "3167",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "pid": "140",
        "address_book": {
            "0": "[SYSTEM]",
            "0/36": "France Culture",
            "0/37": "France Musique",
            "3": "[SYSTEM]",
            "16": "FIP",
            "17": "Mouv'",
            "564": "ICI Gard Loz\u00e8re",
            "565": "ICI Roussillon",
            "566": "ICI Pays Basque",
            "567": "ICI Gascogne",
            "568": "ICI B\u00e9arn Bigorre",
            "569": "ICI Creuse",
            "816": "ICI Berry",
            "817": "ICI Lorraine Sud",
            "818": "ICI Lorraine Nord",
            "819": "ICI Provence",
            "820": "ICI P\u00e9rigord",
            "821": "ICI H\u00e9rault",
            "822": "ICI Gironde",
            "823": "ICI Limousin",
            "824": "ICI La Rochelle",
            "825": "ICI Poitou",
            "857": "[ODA]",
            "858": "[ODA]",
            "859": "[ODA]",
            "930": "ICI Vaucluse",
            "931": "ICI Pays d'Auvergne",
            "932": "ICI Pays de Savoie",
            "933": "ICI Is\u00e8re",
            "934": "ICI Dr\u00f4me Ard\u00e8che",
            "935": "ICI Loire Oc\u00e9an",
            "936": "ICI Mayenne",
            "937": "ICI Cotentin",
            "938": "ICI Normandie (Seine-Maritime - Eure)",
            "939": "ICI Normandie (Calvados - Orne)",
            "940": "ICI Saint-\u00c9tienne Loire",
            "943": "[ODA]",
            "963": "ICI Armorique",
            "964": "France Info",
            "965": "ICI Paris \u00cele-de-France",
            "966": "ICI Nord",
            "967": "France Inter",
            "970": "[ODA]",
            "971": "ICI Occitanie",
            "972": "[ODA]",
            "973": "[ODA]",
            "974": "[ODA]",
            "988": "[ODA]",
            "989": "[ODA]",
            "990": "[ODA]",
            "991": "[ODA]",
            "1005": "ICI Paris \u00cele-de-France",
            "1007": "ICI RCFM",
            "1008": "ICI Breizh Izel",
            "1009": "ICI Touraine",
            "1010": "ICI Orl\u00e9ans",
            "1011": "ICI Champagne-Ardenne",
            "1012": "ICI Bourgogne",
            "1013": "ICI Alsace",
            "1014": "ICI Besan\u00e7on",
            "1015": "ICI Auxerre",
            "1016": "ICI Picardie",
            "1017": "ICI Azur",
            "1018": "ICI Maine",
            "1019": "ICI Belfort-Montb\u00e9liard"
        },
        "psn_book": {}
    },
    {
        "name": "TDF-RDS2 [Eutelsat 5\u00b0W]",
        "src": 1,
        "freq": "11480",
        "pol": "h",
        "sr": "3167",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "pid": "240",
        "address_book": {
            "0": "[SYSTEM]",
            "0/36": "France Culture",
            "0/37": "France Musique",
            "3": "[SYSTEM]",
            "16": "FIP",
            "17": "Mouv'",
            "564": "ICI Gard Loz\u00e8re",
            "565": "ICI Roussillon",
            "566": "ICI Pays Basque",
            "567": "ICI Gascogne",
            "568": "ICI B\u00e9arn Bigorre",
            "569": "ICI Creuse",
            "816": "ICI Berry",
            "817": "ICI Lorraine Sud",
            "818": "ICI Lorraine Nord",
            "819": "ICI Provence",
            "820": "ICI P\u00e9rigord",
            "821": "ICI H\u00e9rault",
            "822": "ICI Gironde",
            "823": "ICI Limousin",
            "824": "ICI La Rochelle",
            "825": "ICI Poitou",
            "857": "[ODA]",
            "858": "[ODA]",
            "859": "[ODA]",
            "930": "ICI Vaucluse",
            "931": "ICI Pays d'Auvergne",
            "932": "ICI Pays de Savoie",
            "933": "ICI Is\u00e8re",
            "934": "ICI Dr\u00f4me Ard\u00e8che",
            "935": "ICI Loire Oc\u00e9an",
            "936": "ICI Mayenne",
            "937": "ICI Cotentin",
            "938": "ICI Normandie (Seine-Maritime - Eure)",
            "939": "ICI Normandie (Calvados - Orne)",
            "940": "ICI Saint-\u00c9tienne Loire",
            "943": "[ODA]",
            "963": "ICI Armorique",
            "964": "France Info",
            "965": "ICI Paris \u00cele-de-France",
            "966": "ICI Nord",
            "967": "France Inter",
            "970": "[ODA]",
            "971": "ICI Occitanie",
            "972": "[ODA]",
            "973": "[ODA]",
            "974": "[ODA]",
            "988": "[ODA]",
            "989": "[ODA]",
            "990": "[ODA]",
            "991": "[ODA]",
            "1005": "ICI Paris \u00cele-de-France",
            "1007": "ICI RCFM",
            "1008": "ICI Breizh Izel",
            "1009": "ICI Touraine",
            "1010": "ICI Orl\u00e9ans",
            "1011": "ICI Champagne-Ardenne",
            "1012": "ICI Bourgogne",
            "1013": "ICI Alsace",
            "1014": "ICI Besan\u00e7on",
            "1015": "ICI Auxerre",
            "1016": "ICI Picardie",
            "1017": "ICI Azur",
            "1018": "ICI Maine",
            "1019": "ICI Belfort-Montb\u00e9liard"
        },
        "psn_book": {}
    },
    {
        "name": "Tiers-RDS [Eutelsat 5°W]",
        "src": 1,
        "freq": "11480",
        "pol": "h",
        "sr": "3167",
        "msys": "dvbs2",
        "mtype_en": True,
        "mtype": "qpsk",
        "fec_en": True,
        "fec": "34",
        "url_pids": "all",
        "pid": "340",
        "address_book": {
            "0": "[SYSTEM]",
            "0/1": "France Inter",
            "0/2": "France Culture",
            "0/3": "France Musique",
            "0/4": "FIP",
            "0/6": "France Info",
            "0/8": "Mouv'",
            "3": "[SYSTEM]",
            "564": "ICI Gard Loz\u00e8re",
            "565": "ICI Roussillon",
            "566": "ICI Pays Basque",
            "567": "ICI Gascogne",
            "568": "ICI B\u00e9arn Bigorre",
            "569": "ICI Creuse",
            "816": "ICI Berry",
            "817": "ICI Lorraine Sud",
            "818": "ICI Lorraine Nord",
            "819": "ICI Provence",
            "820": "ICI P\u00e9rigord",
            "821": "ICI H\u00e9rault",
            "822": "ICI Gironde",
            "823": "ICI Limousin",
            "824": "ICI La Rochelle",
            "825": "ICI Poitou",
            "857": "[ODA]",
            "858": "[ODA]",
            "859": "[ODA]",
            "930": "ICI Vaucluse",
            "931": "ICI Pays d'Auvergne",
            "932": "ICI Pays de Savoie",
            "933": "ICI Is\u00e8re",
            "934": "ICI Dr\u00f4me Ard\u00e8che",
            "935": "ICI Loire Oc\u00e9an",
            "936": "ICI Mayenne",
            "937": "ICI Cotentin",
            "938": "ICI Normandie (Seine-Maritime - Eure)",
            "939": "ICI Normandie (Calvados - Orne)",
            "940": "ICI Saint-\u00c9tienne Loire",
            "943": "[ODA]",
            "963": "ICI Armorique",
            "965": "ICI Paris \u00cele-de-France",
            "966": "ICI Nord",
            "970": "[ODA]",
            "971": "ICI Occitanie",
            "972": "[ODA]",
            "973": "[ODA]",
            "974": "[ODA]",
            "988": "[ODA]",
            "989": "[ODA]",
            "990": "[ODA]",
            "991": "[ODA]",
            "1005": "ICI Paris \u00cele-de-France",
            "1007": "ICI RCFM",
            "1008": "ICI Breizh Izel",
            "1009": "ICI Touraine",
            "1010": "ICI Orl\u00e9ans",
            "1011": "ICI Champagne-Ardenne",
            "1012": "ICI Bourgogne",
            "1013": "ICI Alsace",
            "1014": "ICI Besan\u00e7on",
            "1015": "ICI Auxerre",
            "1016": "ICI Picardie",
            "1017": "ICI Azur",
            "1018": "ICI Maine",
            "1019": "ICI Belfort-Montb\u00e9liard"
        },
        "psn_book": {}
    }
]

# Always update services_default.json to match the current script version
with open("services_default.json", "w", encoding="utf-8") as f:
    json.dump(DEFAULT_SERVICES, f, indent=4)

# Create custom file if it doesn't exist at all
if not os.path.exists("services_custom.json"):
    with open("services_custom.json", "w", encoding="utf-8") as f:
        json.dump(DEFAULT_SERVICES, f, indent=4)

# Load initial config to set deque maxlen correctly on startup
try:
    with open("config.json", "r") as f:
        _init_config = json.load(f)
        _init_max_dis = _init_config.get("max_rows_disabled", False)
        if _init_max_dis:
            _init_max_rows = None
        else:
            _init_max_rows = int(_init_config.get("max_rows", 50000))
except Exception:
    _init_max_rows = 50000

# --- Shared Data for Web Server ---
shared_messages = deque(maxlen=_init_max_rows)
shared_address_book = {}
shared_psn_book = {}
shared_pid_map = {}
shared_services = []
web_clients = []
shared_known_types = {"PI [01]", "PS [02]", "TP/TA [03]", "DI [04]", "M/S [05]", "PTY [07]", "RT [0A]", 
                      "CT [0D]", "AF [13]", "CT [19]", "DSN [1C]", "FF [24]", "IH [25]", "OS [2D]", 
                      "ODA CFG [40]", "ODA FF [42]", "ODA [46]", "DL+ [48]", "DL [AA]"}
shared_hidden_cols = []
shared_green_oda = True
shared_red_ta = True
shared_purple_unknown = True
shared_blue_tech = True
shared_orange_os_ff = True
shared_pink_pi_ps = True
shared_active_services = []
shared_web_username = "admin"
shared_web_password = "admin"
shared_show_date = False
shared_settings_full = {}
shared_services_full = []
main_window_instance = None

from functools import wraps

def check_auth(username, password):
    return username == shared_web_username and password == shared_web_password

def authenticate():
    return Response('Access Denied: Invalid credentials. Please try again.', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- Web Bridge for Remote Control ---
class WebBridge(QObject):
    start_stream = pyqtSignal(str)
    stop_stream = pyqtSignal()
    clear_output = pyqtSignal()
    restart_app = pyqtSignal()

web_bridge = WebBridge()

# --- Flask Web Application ---
from flask import Flask, jsonify, render_template_string, Response, request
flask_app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SatRDS Monitor</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/clusterize.js/0.18.0/clusterize.min.css" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/clusterize.js/0.18.0/clusterize.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f4f9; margin: 0; padding: 20px; }
        h1 { color: #333; margin-bottom: 5px; }
        .controls { display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 20px; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); align-items: center; }
        .control-group { display: flex; align-items: center; gap: 10px; }
        select, input, button, textarea { padding: 8px; font-size: 14px; border-radius: 4px; border: 1px solid #ccc; }
        button { cursor: pointer; font-weight: bold; color: white; border: none; }
        .btn-start { background-color: #4CAF50; }
        .btn-stop { background-color: #F44336; }
        .btn-clear { background-color: #F44336; }
        .btn-export { background-color: #2196F3; }
        table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); table-layout: fixed; }
        th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #ddd; border-right: 1px solid #e0e0e0; word-wrap: break-word; white-space: pre-wrap; }
        th { background-color: #4CAF50; color: white; position: sticky; top: 0; cursor: pointer; user-select: none; border-right: 1px solid #3d8b40; z-index: 2; }
        th:last-child, td:last-child { border-right: none; }
        th:hover { background-color: #45a049; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        tr:hover { background-color: #f1f1f1; }
        .crc-ok { color: green; font-weight: bold; }
        .crc-bad { color: red; font-weight: bold; }
        mark { background-color: #87CEFA; color: black; }
        .text-center { text-align: center; }
        
        .col-time { width: 80px; }
        .col-crc { width: 40px; }
        .col-addr { width: 80px; }
        .col-psn { width: 40px; }
        .col-station { width: 140px; }
        .col-sqc { width: 40px; }
        .col-type { width: 100px; }
        .col-config { width: 180px; }
        .col-data { width: auto; min-width: 250px; }
        .clusterize-no-data td { text-align: center; padding: 40px; color: #888; font-style: italic; background-color: #ffffff; }

        .clusterize-scroll { max-height: 75vh; overflow: auto; }

        /* Modal styling for Type Filter */
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.4); }
        .modal-content { background-color: #fefefe; margin: 8% auto; padding: 20px; border: 1px solid #ccc; width: 380px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
        .type-checkbox-list { max-height: 280px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; margin: 10px 0; background: #fafafa; border-radius: 4px; }
        .type-checkbox-item { margin: 6px 0; display: flex; align-items: center; gap: 8px; }

        /* Tabs styling */
        .tab { overflow: hidden; border: 1px solid #ccc; background-color: #f1f1f1; margin-bottom: 10px; border-radius: 8px; }
        .tab button { background-color: inherit; float: left; border: none; outline: none; cursor: pointer; padding: 10px 16px; transition: 0.3s; font-size: 16px; color: black; font-weight: bold; }
        .tab button:hover { background-color: #ddd; }
        .tab button.active { background-color: #ccc; }
        .tabcontent { display: none; }
    </style>
</head>
<body>
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <h1>SatRDS Monitor</h1>
        <button class="btn-stop" style="height: 35px;" onclick="logout()">Logout</button>
    </div>
    
    <div class="tab">
      <button class="tablinks active" onclick="openTab(event, 'LiveLog')">Full Monitoring</button>
      <button class="tablinks" onclick="openTab(event, 'GridView')">Current Radiotext by station</button>
      <button class="tablinks" onclick="openTab(event, 'Config')">Configuration</button>
    </div>

    <!-- TAB 1 : LIVE LOG -->
    <div id="LiveLog" class="tabcontent" style="display:block;">
        <div class="controls" style="background-color: #e8f5e9;">
            <div class="control-group">
                <label><strong>Status:</strong></label>
                <span id="active-services-badge" style="background: #9E9E9E; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 15px;">No active monitoring.</span>
                <label><strong>Service to monitor:</strong></label>
                <select id="web-service-select"></select>
                <button class="btn-start" onclick="remoteAction('start')">Start Stream</button>
                <button class="btn-stop" onclick="remoteAction('stop')">Stop Stream</button>
            </div>
            <div class="control-group" style="margin-left: auto;">
                <strong id="msg-counter" style="margin-right: 15px; color: #333;">Detections: 0</strong>
                <label style="margin-right: 10px; font-size: 14px; font-weight: bold; cursor: pointer;">
                    <input type="checkbox" id="auto-scroll-toggle" checked> Auto-Scroll
                </label>
                <button class="btn-export" onclick="exportFile('txt')">Export TXT</button>
                <button class="btn-export" onclick="exportFile('csv')">Export CSV</button>
                <button class="btn-clear" onclick="remoteAction('clear')">Clear Output</button>
            </div>
        </div>

        <div class="controls">
            <div class="control-group">
                <label>Address / Station:</label>
                <select id="filter-addr" style="min-width: 200px;" onchange="renderTable()">
                    <option value="ALL">ALL</option>
                    <option value="NOT PRESENT IN DATABASE">NOT PRESENT IN DATABASE</option>
                    <option disabled>---</option>
                </select>
            </div>
            <div class="control-group">
                <label>PSN / Station:</label>
                <select id="filter-psn" style="min-width: 200px;" onchange="renderTable()">
                    <option value="ALL">ALL</option>
                    <option value="NOT PRESENT IN DATABASE">NOT PRESENT IN DATABASE</option>
                    <option disabled>---</option>
                </select>
            </div>
            <div class="control-group">
                <label>Type:</label>
                <button id="btn-web-type-filter" style="background-color: white; color: #333; border: 1px solid #ccc; min-width: 130px;" onclick="toggleTypeModal(true)">ALL</button>
            </div>
            <div class="control-group">
                <label>Search Config / Data:</label>
                <input type="text" id="filter-search" style="min-width: 250px;" placeholder="Keyword..." oninput="renderTable()">
            </div>
        </div>
        
        <div id="scrollArea" class="clusterize-scroll">
            <table>
                <thead>
                    <tr id="table-headers">
                    </tr>
                </thead>
                <tbody id="table-body" class="clusterize-content">
                </tbody>
            </table>
        </div>

        <!-- Fenêtre modale pour le filtre de Types -->
        <div id="type-filter-modal" class="modal">
            <div class="modal-content">
                <h3 style="margin-top:0;">Filter / Exclude Types</h3>
                <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                    <button class="btn-export" style="padding: 4px 8px; font-size: 12px;" onclick="selectAllWebTypes()">Select All</button>
                    <button class="btn-export" style="padding: 4px 8px; font-size: 12px; background-color: #757575;" onclick="deselectAllWebTypes()">Deselect All</button>
                </div>
                <div id="web-type-checkboxes" class="type-checkbox-list"></div>
                <div style="text-align: right; margin-top: 15px;">
                    <button class="btn-start" onclick="toggleTypeModal(false)">Apply Filter</button>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 2 : GRID VIEW -->
    <div id="GridView" class="tabcontent">
        <div class="controls" style="background-color: #e8f5e9;">
            <div class="control-group" style="margin-left: auto;">
                <button class="btn-export" onclick="exportGridFile('txt')">Export TXT</button>
                <button class="btn-export" onclick="exportGridFile('csv')">Export CSV</button>
                <button class="btn-export" onclick="copyGridAll()">Copy All</button>
                <button class="btn-clear" onclick="remoteAction('clear')">Clear Output</button>
            </div>
        </div>
        <table>
            <thead>
                <tr>
                    <th onclick="setGridSort('station')" id="gth-station">Station</th>
                    <th onclick="setGridSort('time')" id="gth-time" style="width: 130px;">Last Update</th>
                    <th onclick="setGridSort('rt')" id="gth-rt">Last Radiotext</th>
                </tr>
            </thead>
            <tbody id="grid-body">
            </tbody>
        </table>
    </div>

    <!-- TAB 3 : CONFIGURATION (VISUAL FORMS) -->
    <div id="Config" class="tabcontent">
        <div style="display: flex; flex-wrap: wrap; gap: 20px;">
            <!-- Main Settings Card -->
            <div class="controls" style="flex: 1; min-width: 320px; display: block;">
                <h3>Main Settings</h3>
                <div style="display: grid; grid-template-columns: 140px 1fr; gap: 8px; align-items: center;">
                    <label>Receiver IP:</label>
                    <input type="text" id="cfg-srv-ip">
                    
                    <label>Minisatip Port:</label>
                    <input type="text" id="cfg-srv-port">
                    
                    <label>OpenWebif Stream Port:</label>
                    <input type="text" id="cfg-ow-port" placeholder="8001">
                    
                    <label>Max Table Rows:</label>
                    <input type="text" id="cfg-max-rows">
                    
                    <label></label>
                    <label><input type="checkbox" id="cfg-max-dis"> Disable the limit</label>
                    
                    <label></label>
                    <label><input type="checkbox" id="cfg-auto-reconnect"> Auto-reconnect on stream loss (10s delay)</label>
                    
                    <label></label>
                    <label><input type="checkbox" id="cfg-ow-extract"> Auto-extract OpenWebif Ref from URL</label>
                    
                    <label>Web Server Port:</label>
                    <input type="text" id="cfg-web-port">
                    
                    <label>Auth. Username:</label>
                    <input type="text" id="cfg-web-user">
                    
                    <label>Auth. Password:</label>
                    <input type="password" id="cfg-web-pass">
                </div>
                <br>
                <div style="display: flex; gap: 10px;">
                    <button class="btn-start" onclick="saveWebSettings()">Save Main & Display Settings</button>
                    <button class="btn-stop" onclick="remoteAction('restart')">Restart Software</button>
                </div>
            </div>

            <!-- Display Settings Card -->
            <div class="controls" style="flex: 1; min-width: 320px; display: block;">
                <h3>Display Settings</h3>
                <label><input type="checkbox" id="cfg-chk-blue"> Display AF / CT / DI / DSN / MS / PTY / PI / PS in light blue</label><br><br>
                <label><input type="checkbox" id="cfg-chk-date"> Display date in Time column</label><br><br>
                <label><input type="checkbox" id="cfg-chk-oda"> Display ODA / IH detections in green</label><br><br>
                <label><input type="checkbox" id="cfg-chk-orange"> Display OS / FF detections in light orange</label><br><br>
                <label><input type="checkbox" id="cfg-chk-pink"> Display other "TP/TA" detections in light red</label><br><br>
                <label><input type="checkbox" id="cfg-chk-red"> Display "TP: ON + TA: ON" detections in dark red</label><br><br>
                <label><input type="checkbox" id="cfg-chk-purple"> Display unknown stations in purple</label><br><br>
                <label><input type="checkbox" id="cfg-chk-hide-addr-psn"> Hide Address & PSN columns for MP2 / AAC streams</label><br><br>
                <label><input type="checkbox" id="cfg-chk-hide-station"> Hide Station column for MP2 / AAC streams</label>
            </div>
        </div>

        <!-- Services & Database Management Card -->
        <div class="controls" style="display: block; margin-top: 15px;">
            <h3>Service & Database Management</h3>
            <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                <!-- Service Form -->
                <div style="flex: 1; min-width: 300px;">
                    <label>Selected Service:</label>
                    <select id="cfg-service-select" onchange="loadWebServiceToForm()" style="width: 100%; margin-bottom: 10px;"></select>
                    
                    <div style="display: grid; grid-template-columns: 120px 1fr; gap: 6px; align-items: center;">
                        <label>Name:</label><input type="text" id="cfg-s-name">
                        <label>Stream Type:</label>
                        <select id="cfg-s-stream-type" onchange="toggleWebSourceUI()">
                            <option value="minisatip">Minisatip</option>
                            <option value="openwebif">OpenWebif</option>
                        </select>
                        <label>OpenWebif Ref:</label><input type="text" id="cfg-s-owref" placeholder="1:0:2:...:0:0:0:" oninput="autoExtractWebRef()">
                        <label>Source:</label><input type="number" id="cfg-s-src" min="1" max="256">
                        <label>Frequency:</label><input type="text" id="cfg-s-freq">
                        <label>Polarization:</label>
                        <select id="cfg-s-pol"><option value="h">Horizontal</option><option value="v">Vertical</option></select>
                        <label>Symbol Rate:</label><input type="text" id="cfg-s-sr">
                        <label>Mod System:</label>
                        <select id="cfg-s-msys"><option value="dvbs">DVB-S</option><option value="dvbs2">DVB-S2</option></select>
                        <label>Mod Type:</label>
                        <select id="cfg-s-mtype"><option value="qpsk">QPSK</option><option value="8psk">8PSK</option><option value="16apsk">16APSK</option><option value="32apsk">32APSK</option></select>
                        <label>FEC:</label>
                        <select id="cfg-s-fec"><option value="12">1/2</option><option value="23">2/3</option><option value="34">3/4</option><option value="35">3/5</option><option value="45">4/5</option><option value="56">5/6</option><option value="78">78</option><option value="89">8/9</option><option value="910">9/10</option></select>
                        <label>Minisatip PIDs:</label><input type="text" id="cfg-s-urlpids" placeholder="all">
                        <label>PID(s) to decode:</label><input type="text" id="cfg-s-pid">
                    </div>
                    <br>
                    <button class="btn-start" onclick="saveWebService()">Save Service</button>
                    <button class="btn-stop" onclick="deleteWebService()">Delete Service</button>
                </div>

                <!-- Database Form for Service -->
                <div style="flex: 1.5; min-width: 350px;">
                    <h4>Address / PSN / PID Database for Selected Service</h4>
                    <div style="max-height: 250px; overflow-y: auto; border: 1px solid #ccc; background: white; margin-bottom: 10px;">
                        <table style="width: 100%;" id="cfg-db-table">
                            <thead><tr><th style="width: 60px;">Type</th><th style="width: 80px;">Value</th><th>Station Name</th><th>Action</th></tr></thead>
                            <tbody id="cfg-db-body"></tbody>
                        </table>
                    </div>
                    <div style="display: flex; gap: 6px; align-items: center;">
                        <select id="cfg-db-new-type"><option value="Address">Address</option><option value="PSN">PSN</option><option value="PID">PID</option></select>
                        <input type="text" id="cfg-db-new-val" placeholder="Value" style="width: 80px;">
                        <input type="text" id="cfg-db-new-name" placeholder="Station Name" style="flex: 1;">
                        <button class="btn-start" onclick="addWebDbEntry()">Add/Update</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        var allMessages = [];
        var filteredMessages = [];
        var gridData = {};
        var knownTypes = new Set();
        var webSelectedTypes = new Set();
        var sortCol = 'time';
        var sortAsc = true;
        var hiddenCols = new Set();
        var greenOda = true;
        var redTa = true;
        var dataObj = null;
        var webServicesList = [];
        var webSettingsObj = {};
        var gridSortCol = 'station';
        var gridSortAsc = true;

        var COLUMNS = [
            { id: 'time', name: 'Time', class: 'col-time' },
            { id: 'crc', name: 'CRC', class: 'col-crc' },
            { id: 'address', name: 'Address', class: 'col-addr' },
            { id: 'psn', name: 'PSN', class: 'col-psn' },
            { id: 'station', name: 'Station', class: 'col-station' },
            { id: 'sqc', name: 'SQC', class: 'col-sqc' },
            { id: 'type', name: 'Type', class: 'col-type' },
            { id: 'config', name: 'Config', class: 'col-config' },
            { id: 'text', name: 'Data', class: 'col-data' }
        ];

        function toggleTypeModal(show) {
            document.getElementById('type-filter-modal').style.display = show ? 'block' : 'none';
        }

        function onWebTypeChange(chk) {
            if (chk.checked) {
                webSelectedTypes.add(chk.value);
            } else {
                webSelectedTypes.delete(chk.value);
            }
            updateTypeButtonLabel();
            renderTable();
        }

        function selectAllWebTypes() {
            knownTypes.forEach(function(t) { webSelectedTypes.add(t); });
            updateTypeFilter();
            renderTable();
        }

        function deselectAllWebTypes() {
            webSelectedTypes.clear();
            var container = document.getElementById("web-type-checkboxes");
            if (container) {
                var chks = container.querySelectorAll("input[type='checkbox']");
                for (var i = 0; i < chks.length; i++) chks[i].checked = false;
            }
            updateTypeButtonLabel();
            renderTable();
        }

        function updateTypeButtonLabel() {
            var btn = document.getElementById("btn-web-type-filter");
            if (!btn) return;
            if (webSelectedTypes.size === knownTypes.size) {
                btn.innerText = "ALL";
            } else if (webSelectedTypes.size === 0) {
                btn.innerText = "None";
            } else {
                var excl = knownTypes.size - webSelectedTypes.size;
                btn.innerText = webSelectedTypes.size + " sel. (" + excl + " excl.)";
            }
        }

        function toggleWebSourceUI() {
            var isOW = document.getElementById('cfg-s-stream-type').value === 'openwebif';
            var owFields = ['cfg-s-owref'];
            var miniFields = ['cfg-s-src', 'cfg-s-freq', 'cfg-s-pol', 'cfg-s-sr', 'cfg-s-msys', 'cfg-s-mtype', 'cfg-s-fec', 'cfg-s-urlpids'];
            
            owFields.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) { 
                    el.style.display = isOW ? '' : 'none'; 
                    if (el.previousElementSibling) el.previousElementSibling.style.display = isOW ? '' : 'none'; 
                }
            });
            miniFields.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) { 
                    el.style.display = isOW ? 'none' : ''; 
                    if (el.previousElementSibling) el.previousElementSibling.style.display = isOW ? 'none' : ''; 
                }
            });
        }

        function autoExtractWebRef() {
            if (webSettingsObj && webSettingsObj.ow_auto_extract) {
                var el = document.getElementById('cfg-s-owref');
                if (el && el.value.includes("ref=")) {
                    var match = el.value.match(/ref=([^&]+)/);
                    if (match) {
                        el.value = match[1].trim();
                    }
                }
            }
        }

        function openTab(evt, tabName) {
            var i, tabcontent, tablinks;
            tabcontent = document.getElementsByClassName("tabcontent");
            for (i = 0; i < tabcontent.length; i++) tabcontent[i].style.display = "none";
            tablinks = document.getElementsByClassName("tablinks");
            for (i = 0; i < tablinks.length; i++) tablinks[i].className = tablinks[i].className.replace(" active", "");
            document.getElementById(tabName).style.display = "block";
            evt.currentTarget.className += " active";
            
            if (tabName === 'Config') {
                fetchFullConfig();
            }
        }

        async function fetchConfig() {
            try {
                var response = await fetch('/api/config');
                var data = await response.json();
                dataObj = data;
                
                hiddenCols = new Set(data.hidden_columns);
                greenOda = data.green_oda_ih;
                redTa = data.red_ta_on;

                var addrGroups = {};
                if (data.address_book) {
                    for (var addr in data.address_book) {
                        var name = data.address_book[addr];
                        if (!addrGroups[name]) addrGroups[name] = [];
                        addrGroups[name].push(addr);
                    }
                }
                var psnGroups = {};
                if (data.psn_book) {
                    for (var psn in data.psn_book) {
                        var namePsn = data.psn_book[psn];
                        if (!psnGroups[namePsn]) psnGroups[namePsn] = [];
                        psnGroups[namePsn].push(psn);
                    }
                }
                
                if (data.active_services && data.active_services.length > 0 && data.full_services) {
                    var activeSvcName = data.active_services[0];
                    var activeSvc = data.full_services.find(function(s) { return s.name === activeSvcName; });
                    if (activeSvc && activeSvc.stream_type === "openwebif" && activeSvc.ow_streams && activeSvc.ow_streams.length > 1) {
                        activeSvc.ow_streams.forEach(function(st) {
                            if (st.name) {
                                if (!addrGroups[st.name]) addrGroups[st.name] = [];
                                if (!psnGroups[st.name]) psnGroups[st.name] = [];
                            }
                        });
                    }
                }

                window.addrGroups = addrGroups;
                window.psnGroups = psnGroups;

                var addrSelect = document.getElementById("filter-addr");
                var currentAddr = addrSelect.value;
                addrSelect.innerHTML = '<option value="ALL">ALL</option><option value="NOT PRESENT IN DATABASE">NOT PRESENT IN DATABASE</option>';
                var sortedAddrNames = Object.keys(addrGroups).sort();
                if (sortedAddrNames.length > 0) {
                    addrSelect.innerHTML += '<option disabled>---</option>';
                    sortedAddrNames.forEach(function(name) {
                        var opt = document.createElement("option");
                        opt.value = name;
                        opt.textContent = name;
                        addrSelect.appendChild(opt);
                    });
                }
                if (addrSelect.querySelector('option[value="' + currentAddr + '"]')) addrSelect.value = currentAddr;

                var psnSelect = document.getElementById("filter-psn");
                var currentPsn = psnSelect.value;
                psnSelect.innerHTML = '<option value="ALL">ALL</option><option value="NOT PRESENT IN DATABASE">NOT PRESENT IN DATABASE</option>';
                var sortedPsnNames = Object.keys(psnGroups).sort();
                if (sortedPsnNames.length > 0) {
                    psnSelect.innerHTML += '<option disabled>---</option>';
                    sortedPsnNames.forEach(function(name) {
                        var opt = document.createElement("option");
                        opt.value = name;
                        opt.textContent = name;
                        psnSelect.appendChild(opt);
                    });
                }
                if (psnSelect.querySelector('option[value="' + currentPsn + '"]')) psnSelect.value = currentPsn;

                if (data.default_types) {
                    data.default_types.forEach(function(t) { knownTypes.add(t); });
                }
                updateTypeFilter();

                var svcSelect = document.getElementById("web-service-select");
                var currentSvc = svcSelect.value;
                svcSelect.innerHTML = '';
                if (data.services) {
                    data.services.forEach(function(svc) {
                        var opt = document.createElement("option");
                        opt.value = svc;
                        opt.textContent = svc;
                        svcSelect.appendChild(opt);
                    });
                }
                if (currentSvc) svcSelect.value = currentSvc;

                var badge = document.getElementById('active-services-badge');
                if (data.active_services && data.active_services.length > 0) {
                    badge.textContent = "Currently monitored: " + data.active_services.join(', ');
                    badge.style.background = "#4CAF50";
                } else {
                    badge.textContent = "No active monitoring.";
                    badge.style.background = "#9E9E9E";
                }

                renderTable();
            } catch(e) {
                console.error("fetchConfig error:", e);
            }
        }

        async function fetchHistory() {
            try {
                var response = await fetch('/api/messages');
                allMessages = await response.json();
                allMessages.forEach(function(msg) {
                    knownTypes.add(msg.type);
                    updateGridData(msg);
                });
                updateTypeFilter();
                renderTable();
                renderGrid();
            } catch(e) {
                console.error("fetchHistory error:", e);
            }
        }

        function updateTypeFilter() {
            var container = document.getElementById("web-type-checkboxes");
            if (!container) return;
            if (!window.typesInitialized && knownTypes.size > 0) {
                knownTypes.forEach(function(t) { webSelectedTypes.add(t); });
                window.typesInitialized = true;
            }
            var html = "";
            Array.from(knownTypes).sort().forEach(function(t) {
                var isChecked = webSelectedTypes.has(t) ? "checked" : "";
                html += '<div class="type-checkbox-item">' +
                    '<label style="cursor:pointer; display:flex; align-items:center; gap:6px;">' +
                        '<input type="checkbox" value="' + escapeHTML(t) + '" ' + isChecked + ' onchange="onWebTypeChange(this)"> ' + escapeHTML(t) +
                    '</label>' +
                '</div>';
            });
            container.innerHTML = html;
            updateTypeButtonLabel();
        }

        function escapeHTML(str) {
            if (!str) return "";
            return String(str).replace(/[&<>'"]/g, function(tag) {
                return {'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'}[tag] || tag;
            });
        }

        function highlightText(text, search) {
            if (!text) return "";
            var escapedText = escapeHTML(text);
            if (!search) return escapedText;
            try {
                var safe = "";
                for (var i = 0; i < search.length; i++) {
                    var ch = search.charAt(i);
                    if (".*+?^${}()|[]/\\\\".indexOf(ch) !== -1) {
                        safe += "\\\\" + ch;
                    } else {
                        safe += ch;
                    }
                }
                var regex = new RegExp(safe, "gi");
                return escapedText.replace(regex, function(match) { return "<mark>" + match + "</mark>"; });
            } catch(e) {
                return escapedText;
            }
        }

        function setSort(col) {
            if (sortCol === col) sortAsc = !sortAsc;
            else { sortCol = col; sortAsc = true; }
            renderTable();
        }

        function parseAddress(addr) {
            if (!addr) return [0, 0];
            var p = addr.split('/');
            return p.length > 1 ? [parseInt(p[0]) || 0, parseInt(p[1]) || 0] : [parseInt(addr) || 0, 0];
        }

        function buildHeaders() {
            var tr = "";
            COLUMNS.forEach(function(col, idx) {
                if (!hiddenCols.has(idx)) {
                    var arrow = "";
                    if (sortCol === col.id) {
                        arrow = sortAsc ? " &#9650;" : " &#9660;";
                    }
                    tr += `<th class="${col.class}" onclick="setSort('${col.id}')">${col.name}${arrow}</th>`;
                }
            });
            var thEl = document.getElementById("table-headers");
            if (thEl) thEl.innerHTML = tr;
        }

        function renderTable() {
            buildHeaders();
            var fAddrEl = document.getElementById("filter-addr");
            var fPsnEl = document.getElementById("filter-psn");
            var fSearchEl = document.getElementById("filter-search");
            var fAddr = fAddrEl ? fAddrEl.value : "ALL";
            var fPsn = fPsnEl ? fPsnEl.value : "ALL";
            var fSearch = fSearchEl ? fSearchEl.value.toLowerCase() : "";
            
            filteredMessages = allMessages.filter(function(msg) {
                if (fAddr === "NOT PRESENT IN DATABASE") {
                    if (dataObj && dataObj.address_book && dataObj.address_book[msg.address]) return false;
                } else if (fAddr !== "ALL") {
                    var addrMatch = window.addrGroups && window.addrGroups[fAddr] && window.addrGroups[fAddr].includes(msg.address);
                    if (!addrMatch && msg.station !== fAddr) return false;
                }
                
                if (fPsn === "NOT PRESENT IN DATABASE") {
                    if (msg.psn && dataObj && dataObj.psn_book && dataObj.psn_book[msg.psn]) return false;
                } else if (fPsn !== "ALL") {
                    var psnMatch = window.psnGroups && window.psnGroups[fPsn] && window.psnGroups[fPsn].includes(msg.psn);
                    if (!psnMatch && msg.station !== fPsn) return false;
                }

                if (webSelectedTypes.size > 0 && !webSelectedTypes.has(msg.type)) return false;
                if (webSelectedTypes.size === 0 && knownTypes.size > 0) return false;

                if (fSearch && !msg.text.toLowerCase().includes(fSearch) && !msg.config.toLowerCase().includes(fSearch)) return false;
                return true;
            });

            if (sortCol) {
                filteredMessages.sort(function(a, b) {
                    var valA, valB;
                    if (sortCol === 'time') {
                        valA = a.timestamp !== undefined ? a.timestamp : a.time;
                        valB = b.timestamp !== undefined ? b.timestamp : b.time;
                    } else if (sortCol === 'sqc' || sortCol === 'psn') { 
                        valA = parseInt(a[sortCol]) || 0; 
                        valB = parseInt(b[sortCol]) || 0; 
                    } else if (sortCol === 'address') {
                        var pA = parseAddress(a.address);
                        var pB = parseAddress(b.address);
                        if (pA[0] !== pB[0]) return (pA[0] - pB[0]) * (sortAsc ? 1 : -1);
                        return (pA[1] - pB[1]) * (sortAsc ? 1 : -1);
                    } else {
                        valA = a[sortCol]; valB = b[sortCol];
                    }
                    if (valA < valB) return sortAsc ? -1 : 1;
                    if (valA > valB) return sortAsc ? 1 : -1;
                    return 0;
                });
            }

            var mcEl = document.getElementById("msg-counter");
            if (mcEl) mcEl.innerText = "Detections: " + allMessages.length;
            var rows = [];
            filteredMessages.forEach(function(msg) {
                var crcClass = msg.crc === '✓' ? 'crc-ok text-center' : 'crc-bad text-center';
                var isUnknown = (msg.station === "Unknown");
                var isOda = ["ODA [46]", "ODA FF [42]", "IH [25]"].includes(msg.type);
                var isBlueTech = ["AF [13]", "CT [0D]", "CT [19]", "DI [04]", "DSN [1C]", "M/S [05]", "PTY [07]", "PI [01]", "PS [02]"].includes(msg.type);
                var isOrange = ["OS [2D]", "FF [24]"].includes(msg.type);
                var isPink = (msg.type === "TP/TA [03]" && msg.text.includes("TA: OFF"));
                var isDarkRed = (msg.type === "TP/TA [03]" && msg.text.includes("TA: ON"));

                var purpleStyle = (dataObj && dataObj.purple_unknown && isUnknown) ? 'style="background-color: #E1BEE7; color: #000000;"' : '';
                
                var rightColStyle = '';
                if (dataObj && dataObj.red_ta_on && isDarkRed) {
                    rightColStyle = 'style="background-color: #C62828; color: #FFFFFF; font-weight: bold;"';
                } else if (greenOda && isOda) {
                    rightColStyle = 'style="background-color: #C8E6C9; color: #000000;"';
                } else if (dataObj && dataObj.blue_tech && isBlueTech) {
                    rightColStyle = 'style="background-color: #BBDEFB; color: #000000;"';
                } else if (dataObj && dataObj.orange_os_ff && isOrange) {
                    rightColStyle = 'style="background-color: #FFE0B2; color: #000000;"';
                } else if (dataObj && dataObj.pink_pi_ps && isPink) {
                    rightColStyle = 'style="background-color: #FCE4EC; color: #000000;"';
                }

                var timeDisp = (dataObj && dataObj.show_date && msg.time_full) ? msg.time_full : msg.time;
                var html = '<tr>';
                if (!hiddenCols.has(0)) html += '<td>' + timeDisp + '</td>';
                if (!hiddenCols.has(1)) html += '<td class="' + crcClass + '">' + msg.crc + '</td>';
                if (!hiddenCols.has(2)) html += '<td ' + purpleStyle + '>' + msg.address + '</td>';
                if (!hiddenCols.has(3)) html += '<td ' + purpleStyle + '>' + msg.psn + '</td>';
                if (!hiddenCols.has(4)) html += '<td ' + purpleStyle + '>' + escapeHTML(msg.station) + '</td>';
                if (!hiddenCols.has(5)) html += '<td>' + msg.sqc + '</td>';
                if (!hiddenCols.has(6)) html += '<td ' + rightColStyle + '>' + msg.type + '</td>';
                if (!hiddenCols.has(7)) html += '<td ' + rightColStyle + '>' + highlightText(msg.config, fSearch) + '</td>';
                if (!hiddenCols.has(8)) html += '<td ' + rightColStyle + '>' + highlightText(msg.text, fSearch) + '</td>';
                html += '</tr>';
                rows.push(html);
            });

            if (rows.length === 0) {
                var visibleCount = 0;
                COLUMNS.forEach(function(col, idx) {
                    if (!hiddenCols.has(idx)) visibleCount++;
                });
                rows.push('<tr class="clusterize-no-data"><td colspan="' + visibleCount + '" style="text-align: center; padding: 40px; color: #888; font-style: italic; background-color: #ffffff;">No data to display for now.</td></tr>');
            }

            if (!window.clusterize) {
                window.clusterize = new Clusterize({
                    rows: rows,
                    scrollId: 'scrollArea',
                    contentId: 'table-body'
                });
            } else {
                window.clusterize.update(rows);
            }

            var autoScrollToggle = document.getElementById('auto-scroll-toggle');
            if (autoScrollToggle && autoScrollToggle.checked) {
                var scrollArea = document.getElementById('scrollArea');
                if (scrollArea) {
                    setTimeout(function() { scrollArea.scrollTop = scrollArea.scrollHeight; }, 0);
                }
            }
        }

        function updateGridData(msg) {
            if (msg.type === "RT [0A]") {
                var st = msg.station === "Unknown" ? ("Unknown (" + msg.address + ")") : msg.station;
                gridData[st] = {
                    rt: msg.text, 
                    time: msg.time, 
                    time_short: msg.time_short || (msg.time ? msg.time.split(' ').pop() : ''), 
                    time_full: msg.time_full || msg.time, 
                    timestamp: msg.timestamp
                };
            }
        }

        function setGridSort(col) {
            if (gridSortCol === col) {
                gridSortAsc = !gridSortAsc;
            } else {
                gridSortCol = col;
                gridSortAsc = true;
            }
            renderGrid();
        }

        function updateGridHeaders() {
            var cols = { 'station': 'Station', 'time': 'Last Update', 'rt': 'Last Radiotext' };
            for (var key in cols) {
                var el = document.getElementById('gth-' + key);
                if (el) {
                    var arrow = "";
                    if (gridSortCol === key) {
                        arrow = gridSortAsc ? " &#9650;" : " &#9660;";
                    }
                    el.innerHTML = cols[key] + arrow;
                }
            }
        }

        function renderGrid() {
            updateGridHeaders();
            var tbody = document.getElementById("grid-body");
            if (!tbody) return;
            
            var entries = Object.keys(gridData).map(function(st) {
                return Object.assign({ station: st }, gridData[st]);
            });

            if (gridSortCol) {
                entries.sort(function(a, b) {
                    var valA, valB;
                    if (gridSortCol === 'time') {
                        valA = a.timestamp !== undefined ? a.timestamp : a.time;
                        valB = b.timestamp !== undefined ? b.timestamp : b.time;
                    } else if (gridSortCol === 'station') {
                        valA = (a.station || '').toLowerCase();
                        valB = (b.station || '').toLowerCase();
                    } else if (gridSortCol === 'rt') {
                        valA = (a.rt || '').toLowerCase();
                        valB = (b.rt || '').toLowerCase();
                    } else {
                        valA = a[gridSortCol];
                        valB = b[gridSortCol];
                    }
                    if (valA < valB) return gridSortAsc ? -1 : 1;
                    if (valA > valB) return gridSortAsc ? 1 : -1;
                    return 0;
                });
            }

            var html = "";
            entries.forEach(function(e) {
                var timeDisp = (dataObj && dataObj.show_date && e.time_full) ? e.time_full : e.time;
                html += '<tr>' +
                    '<td>' + escapeHTML(e.station) + '</td>' +
                    '<td>' + escapeHTML(timeDisp) + '</td>' +
                    '<td>' + escapeHTML(e.rt) + '</td>' +
                '</tr>';
            });
            tbody.innerHTML = html;
        }

        function applyConfigToUI(settings, services) {
            webSettingsObj = settings || {};
            webServicesList = services || [];

            var elSrvIp = document.getElementById('cfg-srv-ip'); if (elSrvIp && !elSrvIp.matches(':focus')) elSrvIp.value = webSettingsObj.server_ip || '';
            var elSrvPort = document.getElementById('cfg-srv-port'); if (elSrvPort && !elSrvPort.matches(':focus')) elSrvPort.value = webSettingsObj.server_port || '8081';
            var elOwPort = document.getElementById('cfg-ow-port'); if (elOwPort && !elOwPort.matches(':focus')) elOwPort.value = webSettingsObj.openwebif_port || '8001';
            var elMaxRows = document.getElementById('cfg-max-rows'); if (elMaxRows && !elMaxRows.matches(':focus')) elMaxRows.value = webSettingsObj.max_rows || 50000;
            var elMaxDis = document.getElementById('cfg-max-dis'); if (elMaxDis) elMaxDis.checked = !!webSettingsObj.max_rows_disabled;
            var elAutoRec = document.getElementById('cfg-auto-reconnect'); if (elAutoRec) elAutoRec.checked = !!webSettingsObj.auto_reconnect;
            var elOwExtract = document.getElementById('cfg-ow-extract'); if (elOwExtract) elOwExtract.checked = !!webSettingsObj.ow_auto_extract;
            var elWebPort = document.getElementById('cfg-web-port'); if (elWebPort && !elWebPort.matches(':focus')) elWebPort.value = webSettingsObj.web_port || '8090';
            var elWebUser = document.getElementById('cfg-web-user'); if (elWebUser && !elWebUser.matches(':focus')) elWebUser.value = webSettingsObj.web_username || 'admin';
            var elWebPass = document.getElementById('cfg-web-pass'); if (elWebPass && !elWebPass.matches(':focus')) elWebPass.value = webSettingsObj.web_password || 'admin';

            var elDate = document.getElementById('cfg-chk-date'); if (elDate) elDate.checked = (webSettingsObj.show_date === true);
            var elOda = document.getElementById('cfg-chk-oda'); if (elOda) elOda.checked = (webSettingsObj.green_oda_ih !== false);
            var elBlue = document.getElementById('cfg-chk-blue'); if (elBlue) elBlue.checked = (webSettingsObj.blue_tech !== false);
            var elOrange = document.getElementById('cfg-chk-orange'); if (elOrange) elOrange.checked = (webSettingsObj.orange_os_ff !== false);
            var elPink = document.getElementById('cfg-chk-pink'); if (elPink) elPink.checked = (webSettingsObj.pink_pi_ps !== false);
            var elRed = document.getElementById('cfg-chk-red'); if (elRed) elRed.checked = (webSettingsObj.red_ta_on !== false);
            var elPurple = document.getElementById('cfg-chk-purple'); if (elPurple) elPurple.checked = (webSettingsObj.purple_unknown !== false);
            var elHideAddrPsn = document.getElementById('cfg-chk-hide-addr-psn'); if (elHideAddrPsn) elHideAddrPsn.checked = (webSettingsObj.hide_addr_psn_audio === true);
            var elHideStation = document.getElementById('cfg-chk-hide-station'); if (elHideStation) elHideStation.checked = (webSettingsObj.hide_station_audio === true);

            var sSelect = document.getElementById('cfg-service-select');
            if (sSelect && sSelect.options.length === 0 && webServicesList.length > 0) {
                sSelect.innerHTML = '';
                webServicesList.forEach(function(s, idx) {
                    var opt = document.createElement('option');
                    opt.value = String(idx);
                    opt.textContent = s.name;
                    sSelect.appendChild(opt);
                });
                sSelect.value = "0";
                loadWebServiceToForm();
            }
        }

        async function fetchFullConfig() {
            try {
                var res = await fetch('/api/config');
                var data = await res.json();
                if (data.full_settings && data.full_services) {
                    applyConfigToUI(data.full_settings, data.full_services);
                }
            } catch(err) {
                console.error("Failed to load config:", err);
            }
        }

        function loadWebServiceToForm() {
            var sSelect = document.getElementById('cfg-service-select');
            if (!sSelect) return;
            var idx = sSelect.value;
            if (idx === '' || idx === null || !webServicesList[idx]) return;
            var s = webServicesList[idx];

            var setVal = function(id, val) { var el = document.getElementById(id); if (el) el.value = val; };

            setVal('cfg-s-name', s.name || '');
            setVal('cfg-s-stream-type', s.stream_type || 'minisatip');
            setVal('cfg-s-owref', s.ow_ref || '');
            setVal('cfg-s-src', s.src || 1);
            setVal('cfg-s-freq', s.freq || '');
            setVal('cfg-s-pol', s.pol || 'h');
            
            toggleWebSourceUI();
            setVal('cfg-s-sr', s.sr || '');
            setVal('cfg-s-msys', s.msys || 'dvbs2');
            setVal('cfg-s-mtype', s.mtype || 'qpsk');
            setVal('cfg-s-fec', s.fec || '34');
            setVal('cfg-s-urlpids', s.url_pids || 'all');
            setVal('cfg-s-pid', s.pid || '');

            renderWebDbTable(s);
        }

        function renderWebDbTable(s) {
            var tbody = document.getElementById('cfg-db-body');
            tbody.innerHTML = '';
            var abook = s.address_book || {};
            var pbook = s.psn_book || {};
            var pidbook = s.pid_book || {};

            for (var addr in abook) {
                var nameA = abook[addr];
                tbody.innerHTML += `<tr><td>Address</td><td>${addr}</td><td>${escapeHTML(nameA)}</td><td><button class="btn-clear" style="padding:2px 6px;" onclick="deleteWebDbEntry('address_book', '${addr}')">X</button></td></tr>`;
            }
            for (var psn in pbook) {
                var nameP = pbook[psn];
                tbody.innerHTML += `<tr><td>PSN</td><td>${psn}</td><td>${escapeHTML(nameP)}</td><td><button class="btn-clear" style="padding:2px 6px;" onclick="deleteWebDbEntry('psn_book', '${psn}')">X</button></td></tr>`;
            }
            for (var pid_val in pidbook) {
                var namePid = pidbook[pid_val];
                tbody.innerHTML += `<tr><td>PID</td><td>${pid_val}</td><td>${escapeHTML(namePid)}</td><td><button class="btn-clear" style="padding:2px 6px;" onclick="deleteWebDbEntry('pid_book', '${pid_val}')">X</button></td></tr>`;
            }
        }

        async function saveWebSettings() {
            var restartNeeded = (
                webSettingsObj.server_ip !== document.getElementById('cfg-srv-ip').value ||
                webSettingsObj.server_port !== document.getElementById('cfg-srv-port').value ||
                webSettingsObj.openwebif_port !== document.getElementById('cfg-ow-port').value ||
                webSettingsObj.web_port !== document.getElementById('cfg-web-port').value ||
                webSettingsObj.web_username !== document.getElementById('cfg-web-user').value ||
                webSettingsObj.web_password !== document.getElementById('cfg-web-pass').value ||
                webSettingsObj.max_rows !== (parseInt(document.getElementById('cfg-max-rows').value) || 50000) ||
                webSettingsObj.max_rows_disabled !== document.getElementById('cfg-max-dis').checked ||
                webSettingsObj.auto_reconnect !== document.getElementById('cfg-auto-reconnect').checked ||
                webSettingsObj.ow_auto_extract !== document.getElementById('cfg-ow-extract').checked
            );

            webSettingsObj.server_ip = document.getElementById('cfg-srv-ip').value;
            webSettingsObj.server_port = document.getElementById('cfg-srv-port').value;
            webSettingsObj.openwebif_port = document.getElementById('cfg-ow-port').value;
            webSettingsObj.max_rows = parseInt(document.getElementById('cfg-max-rows').value) || 50000;
            webSettingsObj.max_rows_disabled = document.getElementById('cfg-max-dis').checked;
            webSettingsObj.auto_reconnect = document.getElementById('cfg-auto-reconnect').checked;
            webSettingsObj.ow_auto_extract = document.getElementById('cfg-ow-extract').checked;
            webSettingsObj.web_port = document.getElementById('cfg-web-port').value;
            webSettingsObj.web_username = document.getElementById('cfg-web-user').value;
            webSettingsObj.web_password = document.getElementById('cfg-web-pass').value;

            webSettingsObj.show_date = document.getElementById('cfg-chk-date').checked;
            webSettingsObj.green_oda_ih = document.getElementById('cfg-chk-oda').checked;
            webSettingsObj.blue_tech = document.getElementById('cfg-chk-blue').checked;
            webSettingsObj.orange_os_ff = document.getElementById('cfg-chk-orange').checked;
            webSettingsObj.pink_pi_ps = document.getElementById('cfg-chk-pink').checked;
            webSettingsObj.red_ta_on = document.getElementById('cfg-chk-red').checked;
            webSettingsObj.purple_unknown = document.getElementById('cfg-chk-purple').checked;
            webSettingsObj.hide_addr_psn_audio = document.getElementById('cfg-chk-hide-addr-psn').checked;
            webSettingsObj.hide_station_audio = document.getElementById('cfg-chk-hide-station').checked;

            await postFullConfig();

            if (restartNeeded) {
                var confirmMsg = "Settings saved successfully." + String.fromCharCode(10) + "Restarting the software is required to apply all changes." + String.fromCharCode(10, 10) + "Do you want to restart it now?";
                if (confirm(confirmMsg)) {
                    remoteAction('restart', true);
                }
            } else {
                alert("Settings saved successfully.");
            }
        }

        async function saveWebService() {
            var idx = document.getElementById('cfg-service-select').value;
            var name = document.getElementById('cfg-s-name').value.trim();
            if (!name) return alert("Service name cannot be empty.\\nPlease check your configuration.");

            var newSvc = {
                name: name,
                stream_type: document.getElementById('cfg-s-stream-type').value,
                ow_ref: document.getElementById('cfg-s-owref').value.trim(),
                src: parseInt(document.getElementById('cfg-s-src').value) || 1,
                freq: document.getElementById('cfg-s-freq').value,
                pol: document.getElementById('cfg-s-pol').value,
                sr: document.getElementById('cfg-s-sr').value,
                msys: document.getElementById('cfg-s-msys').value,
                mtype_en: true,
                mtype: document.getElementById('cfg-s-mtype').value,
                fec_en: true,
                fec: document.getElementById('cfg-s-fec').value,
                url_pids: document.getElementById('cfg-s-urlpids').value || 'all',
                uecp_source: (idx !== '' && webServicesList[idx]) ? (webServicesList[idx].uecp_source || 'pid') : 'pid',
                pid: document.getElementById('cfg-s-pid').value,
                address_book: (idx !== '' && webServicesList[idx]) ? (webServicesList[idx].address_book || {}) : {},
                psn_book: (idx !== '' && webServicesList[idx]) ? (webServicesList[idx].psn_book || {}) : {},
                pid_book: (idx !== '' && webServicesList[idx]) ? (webServicesList[idx].pid_book || {}) : {}
            };

            if (idx !== '' && webServicesList[idx]) {
                webServicesList[idx] = newSvc;
            } else {
                webServicesList.push(newSvc);
            }

            await postFullConfig();
            fetchFullConfig();
            alert("Service saved.");
        }

        async function deleteWebService() {
            var idx = document.getElementById('cfg-service-select').value;
            if (idx === '' || !webServicesList[idx]) return;
            if (!confirm("Are you sure you want to delete service '" + webServicesList[idx].name + "'?")) return;

            webServicesList.splice(idx, 1);
            await postFullConfig();
            fetchFullConfig();
        }

        async function addWebDbEntry() {
            var idx = document.getElementById('cfg-service-select').value;
            if (idx === '' || !webServicesList[idx]) return alert("Please select a service first.");

            var selType = document.getElementById('cfg-db-new-type').value;
            var bType = selType === 'Address' ? 'address_book' : (selType === 'PSN' ? 'psn_book' : 'pid_book');
            var val = document.getElementById('cfg-db-new-val').value.trim();
            var name = document.getElementById('cfg-db-new-name').value.trim();
            if (!val || !name) return alert("Value and Station Name are required.\\nPlease check your configuration.");

            if (!webServicesList[idx][bType]) webServicesList[idx][bType] = {};
            webServicesList[idx][bType][val] = name;

            await postFullConfig();
            renderWebDbTable(webServicesList[idx]);
            document.getElementById('cfg-db-new-val').value = '';
            document.getElementById('cfg-db-new-name').value = '';
        }

        async function deleteWebDbEntry(bType, val) {
            var idx = document.getElementById('cfg-service-select').value;
            if (idx === '' || !webServicesList[idx]) return;
            if (!confirm(`Delete ${val}?`)) return;

            delete webServicesList[idx][bType][val];
            await postFullConfig();
            renderWebDbTable(webServicesList[idx]);
        }

        async function postFullConfig() {
            await fetch('/api/full_config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ settings: webSettingsObj, services: webServicesList })
            });
            fetchConfig();
        }

        function remoteAction(action, skipConfirm) {
            if (action === 'clear' && !confirm("Are you sure you want to clear output?")) return;
            if (action === 'restart' && !skipConfirm && !confirm("Are you sure you want to restart the software?")) return;

            var svc = document.getElementById("web-service-select").value;
            fetch('/api/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cmd: action, service: svc })
            });
            if (action === 'clear') {
                allMessages = [];
                gridData = {};
                if (window.clusterize) window.clusterize.clear();
                renderTable();
                renderGrid();
            } else if (action === 'restart') {
                setTimeout(function() { window.location.reload(); }, 4000);
            }
        }

        function logout() {
            if (confirm("Are you sure you want to logout?")) {
                var xhr = new XMLHttpRequest();
                xhr.open("GET", "/api/config", true, "logout", "logout");
                var redirected = false;
                var doRedirect = function() {
                    if (!redirected) {
                        redirected = true;
                        window.location.href = '/logout';
                    }
                };
                xhr.onreadystatechange = function() {
                    if (xhr.readyState === 4) doRedirect();
                };
                setTimeout(doRedirect, 500);
                xhr.send();
            }
        }

        function copyGridAll() {
            let entries = Object.keys(gridData).map(st => ({ station: st, ...gridData[st] }));
            if (entries.length === 0) { alert("No data to export."); return; }
            const NL = String.fromCharCode(10);
            let text = "";
            entries.forEach(e => {
                const timeDisp = (dataObj && dataObj.show_date && e.time_full) ? e.time_full : e.time;
                text += `${e.station} | ${timeDisp} | ${e.rt || ""}` + NL;
            });
            
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(() => {
                    alert("The visible data has been successfully copied to the clipboard.");
                });
            } else {
                const ta = document.createElement("textarea");
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                try {
                    document.execCommand("copy");
                    alert("The visible data has been successfully copied to the clipboard.");
                } catch(err) {
                    alert("Copy to clipboard failed. Please select and copy manually.");
                }
                document.body.removeChild(ta);
            }
        }

        function exportGridFile(format) {
            let entries = Object.keys(gridData).map(st => ({ station: st, ...gridData[st] }));
            if (entries.length === 0) { alert("No data to export."); return; }
            if (!confirm(`Are you sure you want to export to ${format.toUpperCase()}?`)) return;

            const NL = String.fromCharCode(10);
            let content = "";
            if (format === 'csv') {
                content += "Station,Last Update,Last Radiotext" + NL;
                entries.forEach(e => {
                    const timeDisp = (dataObj && dataObj.show_date && e.time_full) ? e.time_full : e.time;
                    content += `"${e.station.replace(/"/g, '""')}","${timeDisp}","${(e.rt || '').replace(/"/g, '""')}"` + NL;
                });
            } else {
                entries.forEach(e => {
                    const timeDisp = (dataObj && dataObj.show_date && e.time_full) ? e.time_full : e.time;
                    content += `${e.station} | ${timeDisp} | ${e.rt || ""}` + NL;
                });
            }

            const blob = new Blob([content], { type: 'text/plain' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Export_Radiotext_${new Date().getTime()}.${format}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        }

        function exportFile(format) {
            if (filteredMessages.length === 0) {
                alert("No data to export.");
                return;
            }
            if (!confirm(`Are you sure you want to export to ${format.toUpperCase()}?`)) return;

            const NL = String.fromCharCode(10);
            let content = "";
            let head = [];
            COLUMNS.forEach((c, i) => { if (!hiddenCols.has(i)) head.push(c.name); });
            
            if (format === 'csv') {
                content += head.join(",") + NL;
                filteredMessages.forEach(m => {
                    let row = [];
                    if (!hiddenCols.has(0)) row.push(m.time);
                    if (!hiddenCols.has(1)) row.push(m.crc);
                    if (!hiddenCols.has(2)) row.push(m.address);
                    if (!hiddenCols.has(3)) row.push(m.psn);
                    if (!hiddenCols.has(4)) row.push(m.station);
                    if (!hiddenCols.has(5)) row.push(m.sqc);
                    if (!hiddenCols.has(6)) row.push(m.type);
                    if (!hiddenCols.has(7)) row.push(m.config.replace(/"/g, '""'));
                    if (!hiddenCols.has(8)) row.push(m.text.replace(/"/g, '""'));
                    content += row.map(v => `"${v}"`).join(",") + NL;
                });
            } else {
                filteredMessages.forEach(m => {
                    let row = [];
                    if (!hiddenCols.has(0)) row.push(m.time);
                    if (!hiddenCols.has(1)) row.push(m.crc);
                    if (!hiddenCols.has(2)) row.push(m.address);
                    if (!hiddenCols.has(3)) row.push(m.psn);
                    if (!hiddenCols.has(4)) row.push(m.station);
                    if (!hiddenCols.has(5)) row.push(m.sqc);
                    if (!hiddenCols.has(6)) row.push(m.type);
                    if (!hiddenCols.has(7)) row.push(m.config);
                    if (!hiddenCols.has(8)) row.push(m.text);
                    content += row.join(" | ") + NL;
                });
            }
            
            const blob = new Blob([content], { type: 'text/plain' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Export_${new Date().getTime()}.${format}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        }

        var source = new EventSource('/api/stream');
        source.onmessage = function(event) {
            if (event.data === "clear") {
                allMessages = [];
                gridData = {};
                if (window.clusterize) window.clusterize.clear();
                renderTable();
                renderGrid();
                return;
            }
            var msg = JSON.parse(event.data);
            if (msg.stream_error) {
                var badge = document.getElementById('active-services-badge');
                if (badge) {
                    badge.textContent = "Stream Error";
                    badge.style.background = "#F44336";
                }
                alert("Stream Error:" + String.fromCharCode(10, 10) + msg.stream_error);
                return;
            }
            allMessages.push(msg);

            if (allMessages.length > 50000) allMessages.shift();
            
            if (!knownTypes.has(msg.type)) {
                knownTypes.add(msg.type);
                updateTypeFilter();
            }
            updateGridData(msg);
            renderTable();
            renderGrid();
        };

        setInterval(fetchConfig, 5000); 
        fetchConfig();
        fetchHistory();
        fetchFullConfig();
    </script>
</body>
</html>
"""

@flask_app.route('/')
@requires_auth
def index():
    return render_template_string(HTML_TEMPLATE)

@flask_app.route('/logout')
def logout_page():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Logged Out - SatRDS Monitor</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f4f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: white; padding: 30px 40px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; color: #333; font-size: 16px; }
    </style>
</head>
<body>
    <div class="card">
        You have been successfully logged out of the interface.
    </div>
</body>
</html>"""

@flask_app.route('/api/messages')
@requires_auth
def get_messages():
    return jsonify(list(shared_messages))

@flask_app.route('/api/config')
@requires_auth
def get_config():
    global shared_settings_full, shared_services_full, shared_active_services
    return jsonify({
        "address_book": shared_address_book,
        "psn_book": shared_psn_book,
        "services": shared_services,
        "active_services": shared_active_services,
        "default_types": sorted(list(shared_known_types)),
        "hidden_columns": shared_hidden_cols,
        "green_oda_ih": shared_green_oda,
        "red_ta_on": shared_red_ta,
        "purple_unknown": shared_purple_unknown,
        "blue_tech": shared_blue_tech,
        "orange_os_ff": shared_orange_os_ff,
        "pink_pi_ps": shared_pink_pi_ps,
        "show_date": shared_show_date,
        "web_username": shared_web_username,
        "full_settings": shared_settings_full,
        "full_services": shared_services_full
    })

@flask_app.route('/api/full_config', methods=['GET', 'POST'])
def full_config():
    global shared_settings_full, shared_services_full, main_window_instance
    if request.method == 'POST':
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
            
        try:
            payload = request.json
            if "services" in payload:
                shared_services_full = payload["services"]
                if main_window_instance:
                    main_window_instance.services = payload["services"]
                    main_window_instance.save_services()
                else:
                    with open("services_custom.json", "w", encoding="utf-8") as f:
                        json.dump(payload["services"], f, indent=4)
                
            if "settings" in payload:
                s = payload["settings"]
                shared_settings_full.update(s)
                if main_window_instance:
                    main_window_instance.data.update(s)
                    main_window_instance.save_config()
                    main_window_instance.refresh_table_colors()
                    if hasattr(main_window_instance, 'chk_auto_reconnect'):
                        main_window_instance.chk_auto_reconnect.setChecked(s.get("auto_reconnect", False))
                else:
                    with open("config.json", "w", encoding="utf-8") as f:
                        json.dump(s, f, indent=4)

                global shared_web_username, shared_web_password, shared_show_date, shared_green_oda, shared_red_ta, shared_purple_unknown, shared_blue_tech, shared_orange_os_ff, shared_pink_pi_ps, shared_hidden_cols
                shared_web_username = s.get("web_username", shared_web_username)
                shared_web_password = s.get("web_password", shared_web_password)
                shared_show_date = s.get("show_date", False)
                shared_green_oda = s.get("green_oda_ih", True)
                shared_red_ta = s.get("red_ta_on", True)
                shared_purple_unknown = s.get("purple_unknown", True)
                shared_blue_tech = s.get("blue_tech", True)
                shared_orange_os_ff = s.get("orange_os_ff", True)
                shared_pink_pi_ps = s.get("pink_pi_ps", True)
                shared_hidden_cols = s.get("hidden_columns", [])
                
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400
            
    # Retrieves directly from shared variables
    return jsonify({
        "settings": shared_settings_full,
        "services": shared_services_full
    })

@flask_app.route('/api/control', methods=['POST'])
@requires_auth
def control():
    data = request.json
    cmd = data.get('cmd')
    if cmd == 'start':
        web_bridge.start_stream.emit(data.get('service', ''))
    elif cmd == 'stop':
        web_bridge.stop_stream.emit()
    elif cmd == 'clear':
        web_bridge.clear_output.emit()
    elif cmd == 'restart':
        web_bridge.restart_app.emit()
    return jsonify({"status": "ok"})

@flask_app.route('/api/stream')
@requires_auth
def stream():
    def event_stream():
        q = queue.Queue()
        web_clients.append(q)
        try:
            while True:
                msg = q.get()
                if msg == "clear":
                    yield "data: clear\n\n"
                else:
                    yield f"data: {json.dumps(msg)}\n\n"
        except GeneratorExit:
            if q in web_clients:
                web_clients.remove(q)
    return Response(event_stream(), mimetype="text/event-stream")

def run_flask_app(port):
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    try:
        flask_app.run(host='0.0.0.0', port=port, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"The web server has encountered an error.\n\nDetails:\n{e}")

# --- UECP Constants ---
ebu_chars = ['á', 'à', 'é', 'è', 'í', 'ì', 'ó', 'ò', 'ú', 'ù', 'Ñ', 'Ç', 'Ş', 'ß', '¡', 'Ĳ',
             'â', 'ä', 'ê', 'ë', 'î', 'ï', 'ô', 'ö', 'û', 'ü', 'ñ', 'ç', 'ş', 'ğ', 'ı', 'ĳ',
             'ª', 'α', '©', '‰', 'Ğ', 'ě', 'ň', 'ő', 'π', '€', '£', '$', '←', '↑', '→', '↓',
             '⁰', '¹', '²', '³', '±', 'İ', 'ń', 'ű', 'μ', '¿', '÷', '°', '¼', '½', '¾', '§',
             'Á', 'À', 'É', 'È', 'Í', 'Ì', 'Ó', 'Ò', 'Ú', 'Ù', 'Ř', 'Č', 'Š', 'Ž', 'Đ', 'L',
             'Â', 'Ä', 'Ê', 'Ë', 'Î', 'Ï', 'Ô', 'Ö', 'Û', 'Ü', 'ř', 'č', 'š', 'ž', 'đ', 'l',
             'Ã', 'Å', 'Æ', 'Œ', 'ŷ', 'Ý', 'Õ', 'Ø', 'Þ', 'Ŋ', 'Ŕ', 'Ć', 'Ś', 'Ź', 'Ŧ', 'ð',
             'ã', 'å', 'æ', 'œ', 'ŵ', 'ý', 'õ', 'ø', 'þ', 'ŋ', 'ŕ', 'ć', 'ś', 'ź', 'ŧ', 'ÿ']

ptys = ["None","News","Current Affairs","Information","Sport","Education","Drama","Culture",
        "Science","Varied","Pop Music","Rock Music","Easy Listening","Light Classical",
        "Serious Classical","Other Music","Weather","Finance","Children's Programmes",
        "Social Affairs","Religion","Phone-in","Travel","Leisure","Jazz Music","Country Music",
        "National Music","Oldies Music","Folk Music","Documentary","ALARM Test","ALARM!"]

strings = [
    "DUMMY_CLASS", "ITEM_TITLE", "ITEM_ALBUM", "ITEM_TRACKNUMBER", "ITEM_ARTIST", 
    "ITEM_COMPOSITION", "ITEM_MOVEMENT", "ITEM_CONDUCTOR", "ITEM_COMPOSER", "ITEM_BAND", 
    "ITEM_COMMENT", "ITEM_GENRE", "INFO_NEWS", "INFO_NEWS_LOCAL", "INFO_STOCKMARKET", 
    "INFO_SPORT", "INFO_LOTTERY", "INFO_HOROSCOPE", "INFO_DAILY_DIVERSION", "INFO_HEALTH", 
    "INFO_EVENT", "INFO_SZENE", "INFO_CINEMA", "INFO_STUPIDITY_MACHINE", "INFO_DATE_TIME", 
    "INFO_WEATHER", "INFO_TRAFFIC", "INFO_ALARM", "INFO_ADVERTISEMENT", "INFO_URL", 
    "INFO_OTHER", "STATIONNAME_SHORT", "STATIONNAME_LONG", "PROGRAMME_NOW", "PROGRAMME_NEXT", 
    "PROGRAMME_PART", "PROGRAMME_HOST", "PROGRAMME_EDITORIAL_STAFF", "PROGRAMME_FREQUENCY", 
    "PROGRAMME_HOMEPAGE", "PROGRAMME_SUBCHANNEL", "PHONE_HOTLINE", "PHONE_STUDIO", 
    "PHONE_OTHER", "SMS_STUDIO", "SMS_OTHER", "EMAIL_HOTLINE", "EMAIL_STUDIO", "EMAIL_OTHER", 
    "MMS_OTHER", "CHAT", "CHAT_CENTER", "VOTE_QUESTION", "VOTE_CENTER", None, None, None, None, None,
    "PLACE", "APPOINTMENT", "IDENTIFIER", "PURCHASE", "GET_DATA"
]

def crc16_ccitt(data: bytes, poly=0x1021, init_crc=0xFFFF) -> bytes:
    crc = init_crc
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
            crc &= 0xFFFF
    crc = 0xFFFF - crc
    return crc.to_bytes(2, byteorder='big')

# --- Helper logic for Type Normalization on Import ---
def normalize_type_format(t):
    """ Fixes older '0A [RT]' format into new 'RT [0A]' format and 'TA' to 'TP/TA' """
    m = re.match(r"^([0-9A-Fa-f]{2})\s+\[(.*)\]$", t)
    if m:
        new_name = m.group(2)
        if new_name == "TA": new_name = "TP/TA"
        return f"{new_name} [{m.group(1).upper()}]"
    if t == "TA [03]":
        return "TP/TA [03]"
    return t

# --- Custom Qt Elements ---
class TimeTableWidgetItem(QTableWidgetItem):
    """ Custom TableItem to sort time chronologically across midnight using timestamp """
    def __lt__(self, other):
        t1 = self.data(Qt.UserRole)
        t2 = other.data(Qt.UserRole)
        if t1 is not None and t2 is not None:
            return t1 < t2
        return super().__lt__(other)

class NumericTableWidgetItem(QTableWidgetItem):
    """ Custom TableItem to sort numerical addresses and PSN correctly """
    def __lt__(self, other):
        def parse_addr(txt):
            try:
                if not txt: return (0, 0)
                if '/' in txt:
                    p = txt.split('/')
                    return (int(p[0]), int(p[1]))
                return (int(txt), 0)
            except:
                return (0, 0)
        return parse_addr(self.text()) < parse_addr(other.text())

class HighlightDelegate(QStyledItemDelegate):
    """ High-performance delegate with dynamic vertical centering for 1, 2, and 3-line texts at 60 FPS """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search_text = ""
        
    def set_search_text(self, text):
        self.search_text = text.lower()
        
    def paint(self, painter, option, index):
        painter.save()
        bg_brush = index.data(Qt.BackgroundRole)
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        elif bg_brush:
            painter.fillRect(option.rect, bg_brush)
        else:
            bg = option.palette.alternateBase() if (option.features & QStyleOptionViewItem.Alternate) else option.palette.base()
            painter.fillRect(option.rect, bg)

        text = str(index.data() or "")
        if not text:
            painter.restore()
            return

        font = option.font
        painter.setFont(font)
        from PyQt5.QtGui import QFontMetrics
        from PyQt5.QtCore import QRect
        fm = QFontMetrics(font)
        target_width = max(option.rect.width() - 8, 10)

        if self.search_text and self.search_text in text.lower():
            import html
            doc = QTextDocument()
            escaped = html.escape(text)
            pattern = re.compile(re.escape(self.search_text), re.IGNORECASE)
            highlighted = pattern.sub(lambda m: f"<span style='background-color: #87CEFA; color: black;'>{m.group(0)}</span>", escaped)
            
            font = option.font
            doc.setDefaultFont(font)
            doc.setTextWidth(target_width)
            doc.setHtml(f"<div style='white-space: pre-wrap; font-family: inherit;'>{highlighted}</div>")
            
            fg_color = index.data(Qt.ForegroundRole)
            if fg_color:
                doc.setDefaultStyleSheet(f"color: {fg_color.name()};")
                
            doc_height = doc.size().height()
            y_offset = (option.rect.height() - doc_height) / 2 if option.rect.height() > doc_height else 0
            painter.translate(option.rect.left() + 4, option.rect.top() + y_offset)
            
            clip = QRectF(option.rect).translated(-option.rect.left(), -option.rect.top())
            doc.drawContents(painter, clip)
        else:
            fg_color = index.data(Qt.ForegroundRole)
            if option.state & QStyle.State_Selected:
                painter.setPen(option.palette.highlightedText().color())
            elif fg_color:
                painter.setPen(fg_color)
            else:
                painter.setPen(option.palette.text().color())
            
            bound_rect = fm.boundingRect(0, 0, target_width, 0, Qt.TextWordWrap, text)
            text_height = bound_rect.height()
            
            y_offset = max(0, int((option.rect.height() - text_height) / 2))
            draw_rect = QRect(option.rect.left() + 4, option.rect.top() + y_offset, target_width, text_height)
            
            painter.drawText(draw_rect, Qt.AlignLeft | Qt.TextWordWrap, text)

        painter.restore()

class UrlPidsDialog(QDialog):
    """ Dialog to configure custom URL PIDs to avoid UI confusion """
    def __init__(self, current_val, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Minisatip PIDs Configuration")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)

        info_label = QLabel('This feature will modify the "&pids=" value in the Minisatip stream URL.\n'
                            'The value "all" is generally appropriate for most services.\n'
                            'Only change this if you are sure of what you are doing.\n\n'
                            'This value should not be confused with the PID to be specified for decoding ("PID to decode").')
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #222; margin-bottom: 10px;")
        layout.addWidget(info_label)

        self.rb_all = QRadioButton('Default ("all")')
        self.rb_custom = QRadioButton("Custom:")
        self.le_custom = QLineEdit()

        if current_val == "all":
            self.rb_all.setChecked(True)
            self.le_custom.setEnabled(False)
        else:
            self.rb_custom.setChecked(True)
            self.le_custom.setText(current_val)
            self.le_custom.setEnabled(True)

        self.rb_all.toggled.connect(lambda: self.le_custom.setEnabled(not self.rb_all.isChecked()))

        layout.addWidget(self.rb_all)
        h = QHBoxLayout()
        h.addWidget(self.rb_custom)
        h.addWidget(self.le_custom)
        layout.addLayout(h)

        btns = QHBoxLayout()
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def get_value(self):
        if self.rb_all.isChecked():
            return "all"
        return self.le_custom.text().strip() or "all"


mp2_br = [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384]
mp2_sr = [44100, 48000, 32000]

# --- Decoding Thread ---
class DecoderThread(QThread):
    new_message = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, url, pids, uecp_source="pid", station_name="", stream_timeout=10):
        super().__init__()
        self.url = url
        self.target_pids = pids 
        self.uecp_source = uecp_source
        self.station_name = station_name
        self.stream_timeout = stream_timeout
        self.running = True
        self.response = None
        self.uecp_tmps = {}
        self.dl_cache = ''
        self.es_buffers = {}
        
        # Exclusive initialization for the AAC stream via libfaad
        self.aac_handle = None
        if self.uecp_source == "aac" and aac_lib:
            self.aac_cb = UECP_CALLBACK(self.on_aac_uecp_data)
            self.aac_handle = aac_lib.aac_decoder_init(self.aac_cb)

    def stop(self):
        self.running = False
        if self.response:
            try:
                if hasattr(self.response, 'raw') and self.response.raw:
                    self.response.raw.close()
                self.response.close()
            except Exception:
                pass
        self.wait(500)
        
        if self.aac_handle and aac_lib:
            with _aac_feed_lock:
                aac_lib.aac_decoder_close(self.aac_handle)
            self.aac_handle = None

    def run(self):
        self.status_signal.emit("Connecting (waiting for tuner lock)...")
        try:
            with requests.get(self.url, stream=True, timeout=self.stream_timeout) as r:
                self.response = r
                r.raise_for_status()
                self.status_signal.emit(f"Connected to stream. Decoding PID(s): {', '.join(map(str, self.target_pids))}...")
                
                ts_buffer = bytearray()
                for chunk in r.iter_content(chunk_size=32768):
                    if not self.running:
                        break
                    if not chunk:
                        continue
                    ts_buffer.extend(chunk)
                    
                    while len(ts_buffer) >= 188:
                        if ts_buffer[0] != 0x47:
                            sync_idx = ts_buffer.find(b'\x47')
                            if sync_idx == -1:
                                ts_buffer.clear()
                                break
                            del ts_buffer[:sync_idx]
                            if len(ts_buffer) < 188:
                                break
                                
                        pkt = bytes(ts_buffer[:188])
                        del ts_buffer[:188]
                        self.process_ts_packet(pkt)
                
                if self.running:
                    self.error_signal.emit("The stream closed unexpectedly, or no data was received from the receiver.\nPlease check tuner/PID availability and try again.")
                    
        except Exception as e:
            if self.running:
                self.error_signal.emit(f"A connection error occurred.\n\nDetails:\n{str(e)}")
            self.status_signal.emit("Disconnected.")
        finally:
            self.response = None
        self.status_signal.emit("Stopped.")

    def process_ts_packet(self, pkt):
        pktpid = ((pkt[1] & 0x1f) << 8) | pkt[2]
        if pktpid in self.target_pids:
            if self.uecp_source == "pid":
                if (pkt[3] & 0x30) < 0x30:
                    pkt = pkt[6:]
                else:
                    pkt = pkt[pkt[4]+5:]

                uecp_data = self.remove_padding(bytearray(pkt))
                if len(uecp_data) > 0:
                    if pktpid not in self.uecp_tmps:
                        self.uecp_tmps[pktpid] = bytearray()

                    if uecp_data[0] == 0x0 and not self.uecp_tmps[pktpid]:
                        uecp_data = uecp_data[1:]
                    
                    msg_trim_index = self.find_subarray_position(uecp_data, b'\xFF\xEB\x07')
                    if msg_trim_index is not None:
                        uecp_data = uecp_data[msg_trim_index+3:]

                    if uecp_data:
                        uecp_msgs = self.split_uecp_msgs(uecp_data)
                        for msg in uecp_msgs:
                            if msg[0] == 0xFE:
                                self.uecp_tmps[pktpid] = bytearray()
                                if msg[-1] == 0xFF:
                                    self.parse_uecp(msg, pktpid)
                                else:
                                    self.uecp_tmps[pktpid] = msg
                            else:
                                if self.uecp_tmps[pktpid]:
                                    self.uecp_tmps[pktpid] = self.uecp_tmps[pktpid] + msg
                                    if self.uecp_tmps[pktpid][-1] == 0xFF:
                                        self.parse_uecp(self.uecp_tmps[pktpid], pktpid)
                                        self.uecp_tmps[pktpid] = bytearray()
            else:
                self.extract_es_and_decode(pkt, pktpid)

    def extract_es_and_decode(self, pkt, pktpid):
        pusi = bool(pkt[1] & 0x40)
        afc = (pkt[3] >> 4) & 0x3
        if afc & 0x1:
            p_start = (5 + pkt[4]) if (afc & 0x2) else 4
            payload = pkt[p_start:] if p_start < 188 else b''
        else:
            payload = b''

        if payload and pusi:
            if len(payload) >= 9 and payload[:3] == b'\x00\x00\x01':
                pes_hdr_len = payload[8]
                es_start = 9 + pes_hdr_len
                payload = payload[es_start:] if es_start <= len(payload) else b''

        if payload:
            if pktpid not in self.es_buffers:
                self.es_buffers[pktpid] = bytearray()
            self.es_buffers[pktpid].extend(payload)
            self.process_audio_es(pktpid)

    def process_audio_es(self, pktpid):
        if pktpid not in self.uecp_tmps:
            self.uecp_tmps[pktpid] = bytearray()
        if self.uecp_source == "mp2":
            es_buf = self.es_buffers[pktpid]
            while len(es_buf) >= 4:
                sync_pos = -1
                for i in range(len(es_buf) - 1):
                    if es_buf[i] == 0xFF and es_buf[i+1] in (0xFC, 0xFD):
                        sync_pos = i
                        break
                
                if sync_pos == -1:
                    self.es_buffers[pktpid] = es_buf[-1:]
                    break
                if sync_pos > 0:
                    del es_buf[:sync_pos]
                if len(es_buf) < 4:
                    break
                    
                br_index = (es_buf[2] >> 4) & 0xF
                sr_index = (es_buf[2] >> 2) & 0x3
                padding = (es_buf[2] >> 1) & 0x1
                
                if br_index == 0 or br_index >= 15 or sr_index >= 3:
                    del es_buf[0:1]
                    continue
                    
                frame_size = (144 * mp2_br[br_index] * 1000 // mp2_sr[sr_index]) + padding
                
                if len(es_buf) < frame_size:
                    break
                    
                frame = es_buf[:frame_size]
                del es_buf[:frame_size]
                
                pkt_rev = frame[::-1]
                anc_header = pkt_rev[0]
                msg = None
                
                if anc_header == 0xFD:
                    anc_len = pkt_rev[1]
                    if anc_len > 0 and len(pkt_rev) >= 2+anc_len:
                        msg = pkt_rev[2:2+anc_len]
                elif anc_header != 0x00:
                    anc_len = pkt_rev[0]
                    if anc_len > 0 and len(pkt_rev) >= 1+anc_len:
                        msg = pkt_rev[1:1+anc_len]
                        
                if msg:
                    if msg[0] == 0xFE:
                        self.uecp_tmps[pktpid] = bytearray()
                        if msg[-1] == 0xFF:
                            self.parse_uecp(msg, pktpid)
                        else:
                            self.uecp_tmps[pktpid] = msg
                    else:
                        if self.uecp_tmps[pktpid]:
                            self.uecp_tmps[pktpid] = self.uecp_tmps[pktpid] + msg
                            if self.uecp_tmps[pktpid][-1] == 0xFF:
                                self.parse_uecp(self.uecp_tmps[pktpid], pktpid)
                                self.uecp_tmps[pktpid] = bytearray()
        elif self.uecp_source == "aac":
            self.current_msg_pid = pktpid
            es_buf = self.es_buffers[pktpid]
            if self.aac_handle and aac_lib and len(es_buf) >= 8192:
                buffer = (ctypes.c_uint8 * len(es_buf)).from_buffer_copy(es_buf)
                with _aac_feed_lock:
                    aac_lib.aac_decoder_feed(self.aac_handle, buffer, len(es_buf))
                es_buf.clear()

    def on_aac_uecp_data(self, data_ptr, length):
        # Callback invoked natively by the C++ DLL each time a frame is extracted via DSE
        if length > 0:
            data_bytes = bytearray(ctypes.string_at(data_ptr, length))
            
            # Reconstruction using FE/FF markers in case the DLL does not explicitly provide them
            if data_bytes[0] != 0xFE:
                data_bytes = bytearray([0xFE]) + data_bytes
            if data_bytes[-1] != 0xFF:
                data_bytes.append(0xFF)
                
            if len(data_bytes) >= 6:
                uecp_test = self.unescape_uecp(data_bytes)
                if len(uecp_test) >= 6 and crc16_ccitt(bytes(uecp_test[1:-3])) == bytes(uecp_test[-3:-1]):
                    # Precise identification of the thread of the currently active station
                    target_thread = QThread.currentThread()
                    if isinstance(target_thread, DecoderThread):
                        target_thread.parse_uecp(data_bytes, getattr(target_thread, 'current_msg_pid', 0))
                    else:
                        self.parse_uecp(data_bytes, getattr(self, 'current_msg_pid', 0))

    def remove_padding(self, byte_array):
        reversed_byte_array = byte_array[::-1]
        index = next((i for i in range(len(reversed_byte_array) - 1) if reversed_byte_array[i] == 0xFF and reversed_byte_array[i + 1] == 0xFF), None)
        if index is not None:
            return reversed_byte_array[:index][::-1]
        return byte_array

    def split_uecp_msgs(self, byte_array):
        split_arrays = []
        current_array = bytearray()
        for byte in byte_array:
            current_array.append(byte)
            if byte == 0xFF:
                split_arrays.append(current_array)
                current_array = bytearray()
        if current_array:
            split_arrays.append(current_array)
        return split_arrays

    def find_subarray_position(self, main_byte_array, sub_byte_array):
        try:
            return main_byte_array.index(sub_byte_array)
        except ValueError:
            return None

    def unescape_uecp(self, byte_array):
        next_escaped = False
        escaped_array = bytearray()
        for b in byte_array:
            if next_escaped:
                next_escaped = False
                if b+0xFD <= 0xFF:
                    escaped_array.append(b+0xFD)
                else:
                    escaped_array.append(0xFF)
            elif b == 0xFD:
                next_escaped = True
            else:
                escaped_array.append(b)
        return escaped_array

    def parse_uecp(self, byte_array, pid=None):
        time_now = datetime.now()
        time_short = time_now.strftime('%H:%M:%S')
        time_full = time_now.strftime('%d/%m/%Y %H:%M:%S')
        time_str = time_full if shared_show_date else time_short
        time_ts = time_now.timestamp()
        uecp = self.unescape_uecp(byte_array)
        
        if len(uecp) < 6:
            return

        crc_ok = crc16_ccitt(bytes(uecp[1:-3])) == bytes(uecp[-3:-1])
        crc_mark = '✓' if crc_ok else '✗'
        
        addr = (uecp[1] << 8) | uecp[2]
        addr_site = (addr >> 6) & 0x3FF
        addr_enc = addr & 0x3F
        
        if addr_enc == 0:
            formatted_addr = str(addr_site)
        else:
            formatted_addr = f"{addr_site}/{addr_enc}"

        sqc = uecp[3]
        mec = uecp[5]
        mec_desc = "??"
        config_txt = ""
        text = ""
        psn_str = ""
        
        # PSN extraction for MECs who have one
        if mec in [0x02, 0x03, 0x04, 0x05, 0x07, 0x0A, 0x13]:
            if len(uecp) > 7:
                psn_str = str(uecp[7])

        try:
            if mec == 0x01:
                mec_desc = "PI"
                text = uecp[8:-3][0:2].hex().upper()
            elif mec == 0x02:
                mec_desc = "PS"
                config_txt = f"DSN: {uecp[6]} / PSN: {uecp[7]}"
                text = f"[{''.join(chr(c) for c in uecp[8:8+8])}]"
            elif mec == 0x03:
                mec_desc = "TP/TA"
                config_txt = f"DSN: {uecp[6]} / PSN: {uecp[7]}"
                ta = "ON" if uecp[8] & 0x1 else "OFF"
                tp = "ON" if uecp[8] & 0x2 else "OFF"
                text = f"TP: {tp} / TA: {ta}"
            elif mec == 0x04:
                mec_desc = "DI"
                config_txt = f"DSN: {uecp[6]} / PSN: {uecp[7]}"
                ms = "Stereo" if uecp[8] & 0x1 else "Mono"
                ah = "YES" if uecp[8] & 0x2 else "NO"
                cmp = "YES" if uecp[8] & 0x4 else "NO"
                dpty = "YES" if uecp[8] & 0x8 else "NO"
                text = f"Modulation: {ms} / Artificial Head: {ah} / Compressed: {cmp} / Dynamic PTY: {dpty}"
            elif mec == 0x05:
                mec_desc = "M/S"
                config_txt = f"DSN: {uecp[6]} / PSN: {uecp[7]}"
                ms = "M (Music)" if uecp[8] & 0x1 else "S (Speech)"
                text = ms
            elif mec == 0x07:
                mec_desc = "PTY"
                config_txt = f"DSN: {uecp[6]} / PSN: {uecp[7]}"
                text = f"{uecp[8]} | {ptys[uecp[8]]}"
            elif mec == 0x0A:
                mec_desc = "RT"
                config_txt = f"DSN: {uecp[6]} / PSN: {uecp[7]}\nBuffer: {uecp[9]:02X}"
                rt_text = ""
                for c in uecp[10:-3]:
                    if c > 0x7F:
                        rt_text += ebu_chars[c-0x80]
                    else:
                        rt_text += chr(c)
                text = rt_text
            elif mec == 0x0D:
                mec_desc = "CT"
                sign = "-" if uecp[13] & 0x20 else "+"
                offset = (uecp[13] & 0x1F)*0.5
                text = f"{uecp[8]:02d}/{uecp[7]:02d}/{uecp[6]:02d} {uecp[9]:02d}:{uecp[10]:02d}:{uecp[11]:02d}.{uecp[12]:02d} ({sign}{offset})"
            elif mec == 0x2D:
                mec_desc = "OS"
                man_code = uecp[7:9].decode("utf-8", errors='ignore')
                config_txt = f"[{man_code}]"
                os_text = "".join(chr(c) for c in uecp[9:-3] if c >= 32)
                text = os_text
            elif mec == 0x13:
                mec_desc = "AF"
                config_txt = f"DSN: {uecp[6]} / PSN: {uecp[7]}"
                freqs = uecp[11] - 224
                aflist = ", ".join(str((uecp[12+n] + 875) / 10) for n in range(freqs))
                text = f"#{freqs}: {aflist}"
            elif mec == 0x1C:
                mec_desc = "DSN"
                text = f"{uecp[6]:02X}"
            elif mec == 0x19:
                mec_desc = "CT"
                text = "CT Enabled" if uecp[6] else "CT Disabled"
            elif mec == 0x24:
                mec_desc = "FF"
                group_num = (uecp[6] & 0x1E) >> 1
                group_let = "A" if (uecp[6] & 0x01) == 0 else "B"
                buf = (uecp[7] & 0x60) >> 5
                block2 = uecp[7] & 0x1F
                block3 = (uecp[8] << 8) | uecp[9]
                block4 = (uecp[10] << 8) | uecp[11]
                config_txt = f"Group: {group_num}{group_let}\nBUF: {buf}"
                ff_text = "".join(chr(c) for c in uecp[10:12]) if uecp[6] == 0 else ""
                text = f"{block2:02X} {block3:04X} {block4:04X} ({ff_text})"
            elif mec == 0x25:
                mec_desc = "IH"
                group_let = "A" if uecp[6] == 0 else "B"
                buf = (uecp[7] & 0x60) >> 5
                block2 = uecp[7] & 0x1F
                block3 = (uecp[8] << 8) | uecp[9]
                block4 = (uecp[10] << 8) | uecp[11]
                config_txt = f"Group: 6{group_let}\nBUF: {buf}"
                text = f"{block2:02X} {block3:04X} {block4:04X}"
            elif mec == 0x40:
                mec_desc = "ODA CFG"
                group_num = (uecp[6] & 0x1E) >> 1
                group_let = "A" if (uecp[6] & 0x01) == 0 else "B"
                aid = (uecp[7] << 8) | uecp[8]
                config = uecp[9]
                raw = (uecp[10] << 8) | uecp[11]
                timeout = uecp[12]
                timeout_text = f"{timeout}min" if timeout else "0"
                config_txt = f"Group: {group_num}{group_let} -> {aid:04X}\nConfig: {hex(config)}\nTimeout: {timeout_text}"
                text = f"{raw:04X}"
            elif mec == 0x42:
                mec_desc = "ODA FF"
                group_num = (uecp[6] & 0x1E) >> 1
                group_let = "A" if (uecp[6] & 0x01) == 0 else "B"
                block2 = uecp[8]
                block3 = (uecp[9] << 8) | uecp[10]
                block4 = (uecp[11] << 8) | uecp[12]
                config_txt = f"App group: {group_num}{group_let}\nConfig: {hex(uecp[7])}"
                text = f"{block2:02X} {block3:04X} {block4:04X}"
            elif mec == 0x46:
                mec_desc = "ODA"
                aid = (uecp[7] << 8) + uecp[8]
                block2 = uecp[10]
                block3 = (uecp[11] << 8) | uecp[12]
                block4 = (uecp[13] << 8) | uecp[14]
                config_txt = f"AID: {aid:04X}"
                text = f"{block2:02X} {block3:04X} {block4:04X}"
                if aid == 0x4bd7:
                    typ0 = strings[(0x38 & uecp[10] << 3) | uecp[11] >> 5]
                    start0 = (0x3e & uecp[11] << 1) | uecp[12] >> 7
                    len0 = 0x3f & uecp[12] >> 1
                    typ1 = strings[(0x20 & uecp[12] << 5) | uecp[13] >> 3]
                    start1 = (0x38 & uecp[13] << 3) | uecp[14] >> 5
                    len1 = 0x1f & uecp[14]
                    text += f" | Tag1: {typ0} {start0},{len0} | Tag2: {typ1} {start1},{len1}"
            elif mec == 0x48:
                mec_desc = "DL+"
                if len(self.dl_cache) > 0:
                    dlplus = uecp[9:-3]
                    tags = []
                    for i in range(0, len(dlplus), 3):
                        chunk = dlplus[i:i+3]
                        if chunk[0] != 0:
                            tags.append(f"Tag {chunk[0]}: {self.dl_cache[chunk[1]:chunk[1]+1+chunk[2]]}")
                    text = "\n".join(tags)
            elif mec == 0xAA:
                mec_desc = "DL"
                dl_text = ""
                for c in uecp[8:-3]:
                    if c > 0x7F:
                        dl_text += ebu_chars[c-0x80]
                    else:
                        dl_text += chr(c)
                self.dl_cache = dl_text
                text = dl_text
            else:
                text = str([f'{byte:02x}' for byte in uecp[6:-3]])

        except Exception as e:
            text = f"A parse error has occurred.\n\nDetails:\n{e}"
            
        # Targeted resolution based specifically on the packet's source PID.
        service_books = shared_pid_map.get(pid, {})
        a_book = service_books.get("address_book", {})
        p_book = service_books.get("psn_book", {})
        default_st = service_books.get("default_station", "")

        station = None
        if psn_str and psn_str in p_book:
            station = p_book[psn_str]
        elif formatted_addr in a_book:
            station = a_book[formatted_addr]
        elif psn_str and psn_str in shared_psn_book:
            station = shared_psn_book[psn_str]
        elif formatted_addr in shared_address_book:
            station = shared_address_book[formatted_addr]
        elif self.station_name:
            station = self.station_name
        elif default_st:
            station = default_st
        else:
            station = "Unknown"

        msg_data = {
            "time": time_str,
            "time_short": time_short,
            "time_full": time_full,
            "timestamp": time_ts,
            "crc": crc_mark,
            "address": formatted_addr,
            "psn": psn_str,
            "sqc": str(sqc),
            "type": f"{mec_desc} [{mec:02X}]", 
            "config": config_txt,
            "text": text,
            "station": station
        }
        self.new_message.emit(msg_data)

class BouquetLineEdit(QLineEdit):
    """ Secured input field: preserves horizontal scrolling and smooth navigation while preventing full selection on click """
    def __init__(self, placeholder="", max_width=None, parent=None):
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        if max_width:
            self.setMaximumWidth(max_width)
        self.setDragEnabled(False)

    def mousePressEvent(self, event):
        had_focus = self.hasFocus()
        super().mousePressEvent(event)
        # Immediately removes the automatic full selection triggered when the element gains focus upon clicking
        if not had_focus and event.button() == Qt.LeftButton:
            self.deselect()

class OpenWebifBouquetDialog(QDialog):
    def __init__(self, streams, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OpenWebif Bouquet Configuration")
        self.setMinimumSize(640, 420)
        self.streams = [dict(s) for s in streams]
        
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Station Name", "OpenWebif Ref", "UECP Source", "PID"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(False)
        layout.addWidget(self.table)
        
        self.populate_table()
        
        # Input line/box
        form = QHBoxLayout()
        self.e_name = BouquetLineEdit("Station Name")
        self.e_ref = BouquetLineEdit("1:0:A:...")
        self.e_ref.textChanged.connect(self.on_eref_text_changed)
        self.c_src = QComboBox()
        self.c_src.addItem("Dedicated PID", "pid")
        self.c_src.addItem("Audio AAC", "aac")
        self.c_src.addItem("Audio MP2", "mp2")
        self.e_pid = BouquetLineEdit("PID", max_width=60)
        
        form.addWidget(self.e_name)
        form.addWidget(self.e_ref)
        form.addWidget(self.c_src)
        form.addWidget(self.e_pid)
        layout.addLayout(form)
        
        self.table.itemSelectionChanged.connect(self.on_select)
        
        # Bottom button bar
        btn_box = QHBoxLayout()
        btn_add = QPushButton("Add")
        btn_update = QPushButton("Update")
        btn_del = QPushButton("Delete")
        btn_add.clicked.connect(self.add_stream)
        btn_update.clicked.connect(self.update_stream)
        btn_del.clicked.connect(self.del_stream)

        ok_btn = QPushButton("Save Bouquet")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        btn_box.addWidget(btn_add)
        btn_box.addWidget(btn_update)
        btn_box.addWidget(btn_del)
        btn_box.addStretch()
        btn_box.addWidget(ok_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def on_eref_text_changed(self, text):
        parent = self.parent()
        if parent and hasattr(parent, 'data') and parent.data.get("ow_auto_extract", False) and "ref=" in text:
            match = re.search(r'ref=([^&]+)', text)
            if match:
                extracted = match.group(1).strip()
                if extracted != text:
                    self.e_ref.blockSignals(True)
                    self.e_ref.setText(extracted)
                    self.e_ref.blockSignals(False)

    @staticmethod
    def get_display_source(raw_val):
        mapping = {"pid": "Dedicated PID", "aac": "Audio AAC", "mp2": "Audio MP2"}
        return mapping.get(raw_val, raw_val)
        
    def populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        # Alphabetical sort (A–Z) of the source list
        self.streams.sort(key=lambda x: x.get("name", "").lower())
        for s in self.streams:
            r = self.table.rowCount()
            self.table.insertRow(r)
            item_name = QTableWidgetItem(s.get("name", ""))
            item_name.setData(Qt.UserRole, s)  # Memorize the exact reference of the station
            self.table.setItem(r, 0, item_name)
            self.table.setItem(r, 1, QTableWidgetItem(s.get("ref", "")))
            src_display = self.get_display_source(s.get("uecp_source", "pid"))
            self.table.setItem(r, 2, QTableWidgetItem(src_display))
            self.table.setItem(r, 3, NumericTableWidgetItem(s.get("pid", "")))
        # Forces the indicator and the actual sort from A to Z (Ascending).
        self.table.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.AscendingOrder)
            
    def on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            r = rows[0].row()
            self.e_name.setText(self.table.item(r, 0).text())
            self.e_ref.setText(self.table.item(r, 1).text())
            src_text = self.table.item(r, 2).text()
            idx = self.c_src.findText(src_text)
            if idx >= 0: self.c_src.setCurrentIndex(idx)
            self.e_pid.setText(self.table.item(r, 3).text())
            
    def add_stream(self):
        name = self.e_name.text().strip()
        ref = self.e_ref.text().strip()
        if not name or not ref:
            QMessageBox.warning(self, "Error", "Station Name and OpenWebif Ref values are missing.\nPlease check your configuration.")
            return
        new_s = {
            "name": name,
            "ref": ref,
            "uecp_source": self.c_src.currentData(),
            "pid": self.e_pid.text().strip()
        }
        self.streams.append(new_s)
        self.populate_table()
        self.e_name.clear()
        self.e_ref.clear()
        self.e_pid.clear()
        
    def update_stream(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Error", "Please select a station in the table to update.")
            return
        r = rows[0].row()
        item_0 = self.table.item(r, 0)
        if not item_0: return
        target_dict = item_0.data(Qt.UserRole)
        
        name = self.e_name.text().strip()
        ref = self.e_ref.text().strip()
        if not name or not ref:
            QMessageBox.warning(self, "Error", "Station Name and OpenWebif Ref are required.")
            return
            
        new_s = {
            "name": name,
            "ref": ref,
            "uecp_source": self.c_src.currentData(),
            "pid": self.e_pid.text().strip()
        }
        
        # Update of the exact object in memory
        if target_dict and target_dict in self.streams:
            idx = self.streams.index(target_dict)
            self.streams[idx] = new_s
        elif r < len(self.streams):
            self.streams[r] = new_s
            
        self.populate_table()
        # Reselect the line that was updated previously
        for i in range(self.table.rowCount()):
            it = self.table.item(i, 0)
            if it and it.text() == name:
                self.table.selectRow(i)
                break
        
    def del_stream(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            r = rows[0].row()
            item_0 = self.table.item(r, 0)
            target_dict = item_0.data(Qt.UserRole) if item_0 else None
            if target_dict and target_dict in self.streams:
                self.streams.remove(target_dict)
            elif r < len(self.streams):
                del self.streams[r]
            self.populate_table()
            self.e_name.clear()
            self.e_ref.clear()
            self.e_pid.clear()

    def reject(self):
        # Asks confirmation when cancelling or closing the package window
        reply = QMessageBox.question(
            self, 
            "Cancel Bouquet Configuration", 
            "Are you sure you want to cancel?\nUnsaved changes will be lost.", 
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            super().reject()

    def get_streams(self):
        # Retrieves the feeds in the order displayed on the screen (if the user has clicked a column to sort)
        ordered_streams = []
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0).text() if self.table.item(r, 0) else ""
            ref = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            src_display = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            raw_src = "pid"
            if "AAC" in src_display: raw_src = "aac"
            elif "MP2" in src_display: raw_src = "mp2"
            pid = self.table.item(r, 3).text() if self.table.item(r, 3) else ""
            if name or ref:
                ordered_streams.append({"name": name, "ref": ref, "uecp_source": raw_src, "pid": pid})
        return ordered_streams if ordered_streams else self.streams

class InitialSetupWizard(QDialog):
    """ Wizard displayed at first startup """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Initial Setup")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)

        lbl = QLabel("Welcome to SatRDS Monitor!\n\nPlease configure your receiver settings to get started.\nYou can leave the ports empty if you do not use them.")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("margin-bottom: 15px;")
        layout.addWidget(lbl)

        form = QFormLayout()
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("")
        self.mini_port_input = QLineEdit("8081")
        self.ow_port_input = QLineEdit("8001")

        form.addRow("Receiver IP:", self.ip_input)
        form.addRow("Minisatip Port:", self.mini_port_input)
        form.addRow("OpenWebif Stream Port:", self.ow_port_input)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save and Apply")
        btn_save.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        btn_save.setDefault(True)
        btn_skip = QPushButton("Skip (Configure Later)")
        btn_save.clicked.connect(self.accept)
        btn_skip.clicked.connect(self.reject)

        btns.addWidget(btn_skip)
        btns.addWidget(btn_save)
        layout.addLayout(btns)

    def get_data(self):
        return self.ip_input.text().strip(), self.mini_port_input.text().strip(), self.ow_port_input.text().strip()

class DisplaySettingsDialog(QDialog):
    """ Dedicated window for display and column options """
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main = main_window
        self.setWindowTitle("Display and Column Settings")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        form.addRow(QLabel("<b>Display & Colors:</b>"))
        form.addRow(self.main.chk_blue_tech)
        form.addRow(self.main.chk_show_date)
        form.addRow(self.main.chk_green_oda)
        form.addRow(self.main.chk_orange_os_ff)
        form.addRow(self.main.chk_pink_pi_ps)
        form.addRow(self.main.chk_red_ta)
        form.addRow(self.main.chk_purple_unknown)
        form.addRow(self.main.chk_hide_addr_psn_audio)
        form.addRow(self.main.chk_hide_station_audio)
        
        form.addRow(QLabel("<b><br>Visible Columns:</b>"))
        for chk in self.main.col_chks:
            form.addRow(chk)
            
        layout.addLayout(form)
        
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("Close")
        ok_btn.clicked.connect(self.accept)
        btn_box.addStretch()
        btn_box.addWidget(ok_btn)
        layout.addLayout(btn_box)

class TypeFilterDialog(QDialog):
    """ Dialog box to include or exclude RDS/UECP frame types """
    def __init__(self, known_types, selected_types, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filter / Exclude Types")
        self.setMinimumSize(420, 460)
        self.known_types = sorted(list(known_types))
        self.selected_types = set(selected_types)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Uncheck types to exclude them from real-time monitoring:"))
        
        btn_h = QHBoxLayout()
        b_all = QPushButton("Select All")
        b_none = QPushButton("Deselect All")
        b_all.clicked.connect(self.select_all)
        b_none.clicked.connect(self.deselect_all)
        btn_h.addWidget(b_all)
        btn_h.addWidget(b_none)
        layout.addLayout(btn_h)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        self.form = QVBoxLayout(scroll_widget)
        
        self.chks = {}
        for t in self.known_types:
            chk = QCheckBox(t)
            chk.setChecked(t in self.selected_types)
            self.chks[t] = chk
            self.form.addWidget(chk)
            
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        bb = QHBoxLayout()
        ok = QPushButton("Apply Filter")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.apply_and_close)
        cancel.clicked.connect(self.reject)
        bb.addStretch()
        bb.addWidget(ok)
        bb.addWidget(cancel)
        layout.addLayout(bb)
        
    def select_all(self):
        for chk in self.chks.values():
            chk.setChecked(True)
            
    def deselect_all(self):
        for chk in self.chks.values():
            chk.setChecked(False)
            
    def apply_and_close(self):
        self.selected_types = {t for t, chk in self.chks.items() if chk.isChecked()}
        self.accept()
        
    def get_selected(self):
        return self.selected_types

class LogTableModel(QAbstractTableModel):
    """ Ultra-lightweight virtualized data model ensuring 60 FPS and minimal RAM consumption even with 50,000+ rows """
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self._all_rows = []
        self._filtered_rows = []
        self._headers = ["Time", "CRC", "Address", "PSN", "Station", "SQC", "Type", "Config", "Data"]

    def rowCount(self, parent=QModelIndex()):
        return len(self._filtered_rows)

    def columnCount(self, parent=QModelIndex()):
        return 9

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._headers[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._filtered_rows):
            return None
            
        row_data = self._filtered_rows[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return row_data["time_full"] if (self.main.chk_show_date.isChecked() and "time_full" in row_data) else row_data["time"]
            elif col == 1: return row_data.get("crc", "")
            elif col == 2: return row_data.get("address", "")
            elif col == 3: return row_data.get("psn", "")
            elif col == 4: return row_data.get("station", "")
            elif col == 5: return row_data.get("sqc", "")
            elif col == 6: return row_data.get("type", "")
            elif col == 7: return row_data.get("config", "")
            elif col == 8: return row_data.get("text", "")

        elif role == Qt.TextAlignmentRole:
            if col == 1:
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        elif role == Qt.BackgroundRole:
            station = row_data.get("station", "")
            msg_type = row_data.get("type", "")
            data_text = row_data.get("text", "")

            if self.main.chk_purple_unknown.isChecked() and station == "Unknown" and col in (2, 3, 4):
                return QColor("#E1BEE7")

            if col in (6, 7, 8):
                is_tp_on = "TP: ON" in data_text
                is_ta_on = "TA: ON" in data_text

                if self.main.chk_red_ta.isChecked() and msg_type == "TP/TA [03]" and is_tp_on and is_ta_on:
                    return QColor("#C62828")
                elif self.main.chk_pink_pi_ps.isChecked() and msg_type == "TP/TA [03]" and not (is_tp_on and is_ta_on):
                    return QColor("#FFCDD2")
                elif self.main.chk_green_oda.isChecked() and msg_type in ["ODA [46]", "ODA FF [42]", "IH [25]"]:
                    return QColor("#C8E6C9")
                elif self.main.chk_blue_tech.isChecked() and msg_type in ["AF [13]", "CT [0D]", "CT [19]", "DI [04]", "DSN [1C]", "M/S [05]", "PTY [07]", "PI [01]", "PS [02]"]:
                    return QColor("#BBDEFB")
                elif self.main.chk_orange_os_ff.isChecked() and msg_type in ["OS [2D]", "FF [24]"]:
                    return QColor("#FFE0B2")

        elif role == Qt.ForegroundRole:
            if col in (6, 7, 8):
                msg_type = row_data.get("type", "")
                data_text = row_data.get("text", "")
                if self.main.chk_red_ta.isChecked() and msg_type == "TP/TA [03]" and "TP: ON" in data_text and "TA: ON" in data_text:
                    return QColor("#FFFFFF")
            return QColor("#000000")

        elif role == Qt.ToolTipRole:
            if col == 7 and row_data.get("type") == "RT [0A]":
                buf_match = re.search(r"(?:BUF|Buffer):\s*([0-9a-fA-F]{2})", row_data.get("config", ""))
                if buf_match:
                    buf_val = int(buf_match.group(1), 16)
                    b_cfg = (buf_val >> 5) & 0x03
                    b_tx = (buf_val >> 1) & 0x0F
                    b_ab = buf_val & 0x01
                    cfg_str = "Clear buffer, add message" if b_cfg == 0 else "Append message to buffer" if b_cfg == 2 else "Unknown config"
                    tx_str = "Indefinite transmissions" if b_tx == 0 else f"{b_tx} transmission(s)"
                    ab_str = "Toggle A/B flag" if b_ab == 1 else "Don't toggle A/B flag"
                    return f"Buffer Configuration:\n- {cfg_str}\n- {tx_str}\n- {ab_str}"
                return "Buffer configuration is unknown.\nNo information available."

        elif role == Qt.UserRole:
            return row_data

        return None

    def sort(self, column, order=Qt.AscendingOrder):
        self.beginResetModel()
        reverse = (order == Qt.DescendingOrder)
        
        def parse_addr(addr):
            try:
                if not addr: return (0, 0)
                if '/' in addr:
                    p = addr.split('/')
                    return (int(p[0]), int(p[1]))
                return (int(addr), 0)
            except:
                return (0, 0)

        if column == 0:
            self._filtered_rows.sort(key=lambda r: r.get("timestamp", 0), reverse=reverse)
        elif column in (1, 4, 6, 7, 8):
            key_name = {1: "crc", 4: "station", 6: "type", 7: "config", 8: "text"}[column]
            self._filtered_rows.sort(key=lambda r: str(r.get(key_name, "")).lower(), reverse=reverse)
        elif column == 2:
            self._filtered_rows.sort(key=lambda r: parse_addr(r.get("address", "")), reverse=reverse)
        elif column in (3, 5):
            key_name = "psn" if column == 3 else "sqc"
            self._filtered_rows.sort(key=lambda r: int(r.get(key_name, 0) or 0), reverse=reverse)
            
        self.endResetModel()

    def append_batch(self, msgs, filter_fn):
        if not msgs:
            return False
            
        matched = []
        for m in msgs:
            self._all_rows.append(m)
            if filter_fn is None or filter_fn(m):
                matched.append(m)
                
        limit = self.main.data.get("max_rows", 50000)
        disabled = self.main.data.get("max_rows_disabled", False)
        if not disabled and len(self._all_rows) > limit:
            # Batch purge to avoid intensive recalculation and freezing on every frame once the limit is reached
            excess = len(self._all_rows) - limit
            purge_amount = max(excess, int(limit * 0.1))
            del self._all_rows[:purge_amount]
            self.reapply_filter(filter_fn)
            return bool(matched)

        if matched:
            start = len(self._filtered_rows)
            end = start + len(matched) - 1
            self.beginInsertRows(QModelIndex(), start, end)
            self._filtered_rows.extend(matched)
            self.endInsertRows()
            return True
        return False

    def reapply_filter(self, filter_fn=None):
        if filter_fn is None:
            filter_fn = self.main.check_msg_filter
        self.beginResetModel()
        self._filtered_rows = [m for m in self._all_rows if filter_fn(m)]
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._all_rows.clear()
        self._filtered_rows.clear()
        self.endResetModel()

# --- Main GUI Application ---
class MainWindow(QMainWindow):
    def __init__(self):
        global main_window_instance
        global shared_address_book
        global shared_psn_book
        global shared_services
        global shared_hidden_cols
        global shared_green_oda
        global shared_red_ta
        global shared_purple_unknown
        global shared_blue_tech
        global shared_orange_os_ff
        global shared_pink_pi_ps
        global shared_web_username
        global shared_web_password
        global shared_show_date
        global shared_settings_full
        global shared_services_full

        main_window_instance = self
        
        super().__init__()
        self.setWindowTitle("SatRDS Monitor")
        
        self.config_file = "config.json"
        self.config_exists = os.path.exists(self.config_file)
        self.data = {
            "server_ip": "", 
            "server_port": "8081",
            "openwebif_port": "8001",
            "web_enable": False,
            "web_port": "8090",
            "web_username": "admin",
            "web_password": "admin",
            "show_date": False,
            "sort_services_alpha": False,
            "max_rows": 50000,
            "max_rows_disabled": False,
            "green_oda_ih": True,
            "red_ta_on": True,
            "purple_unknown": True,
            "blue_tech": True,
            "orange_os_ff": True,
            "pink_pi_ps": True,
            "hide_addr_psn_audio": False,
            "hide_station_audio": False,
            "hidden_columns": [],
            "column_widths": [70, 40, 75, 40, 150, 40, 100, 180],
            "grid_column_widths": [150, 130],
            "db_column_widths": [70, 75],
            "db_sort_col": 0,
            "db_sort_order": 0,
            "window_width": 1300,
            "window_height": 750,
            "window_maximized": True,
            "auto_reconnect": False,
            "ow_auto_extract": True
        }
        self.load_config()
        
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.timeout.connect(self.do_reconnect)
        
        self.resize(self.data.get("window_width", 1300), self.data.get("window_height", 750))
        if self.data.get("window_maximized", False):
            self.setWindowState(Qt.WindowMaximized)
            
        self.load_services()
        
        shared_address_book = {}
        shared_psn_book = {}
        shared_services = [s["name"] for s in self.services]
        shared_hidden_cols = self.data.get("hidden_columns", [])
        shared_green_oda = self.data.get("green_oda_ih", True)
        shared_red_ta = self.data.get("red_ta_on", True)
        shared_purple_unknown = self.data.get("purple_unknown", True)
        shared_blue_tech = self.data.get("blue_tech", True)
        shared_orange_os_ff = self.data.get("orange_os_ff", True)
        shared_pink_pi_ps = self.data.get("pink_pi_ps", True)
        shared_web_username = self.data.get("web_username", "admin")
        shared_web_password = self.data.get("web_password", "admin")
        shared_show_date = self.data.get("show_date", False)
        shared_settings_full = self.data
        shared_services_full = self.services

        self.active_threads = []
        self.flask_thread = None
        self.current_url_pids = "all"
        self.msg_count = 0
        self.current_loaded_service = ""
        self.current_ow_streams = []
        self.editing_service_name = ""
        self.prev_selected_names = []
        self.bypass_change_confirmation = False
        
        # Qqueue and timer for scrolling smoothness
        self.msg_queue = queue.Queue()
        self.gui_timer = QTimer(self)
        self.gui_timer.timeout.connect(self.process_msg_queue)
        self.gui_timer.start(15)
        
        # Pre-initialize UI combos for safe early updating
        self.filter_combo = QComboBox()
        self.filter_combo.setMinimumWidth(200)
        self.filter_combo.addItem("ALL")
        self.filter_combo.addItem("NOT PRESENT IN DATABASE")
        self.filter_combo.insertSeparator(2)
        self.filter_combo.currentTextChanged.connect(self.apply_filter)
        
        self.filter_psn_combo = QComboBox()
        self.filter_psn_combo.setMinimumWidth(200)
        self.filter_psn_combo.addItem("ALL")
        self.filter_psn_combo.addItem("NOT PRESENT IN DATABASE")
        self.filter_psn_combo.insertSeparator(2)
        self.filter_psn_combo.currentTextChanged.connect(self.apply_filter)

        self.known_types = set(["PI [01]", "PS [02]", "TP/TA [03]", "DI [04]", "M/S [05]", "PTY [07]", "RT [0A]", 
                                "CT [0D]", "AF [13]", "CT [19]", "DSN [1C]", "FF [24]", "IH [25]", "OS [2D]", 
                                "ODA CFG [40]", "ODA FF [42]", "ODA [46]", "DL+ [48]", "DL [AA]"])
        saved_types = self.data.get("selected_types", None)
        if saved_types is not None:
            self.selected_types = set(saved_types)
        else:
            self.selected_types = set(self.known_types)
            
        self.btn_type_filter = QPushButton("ALL")
        self.btn_type_filter.setMinimumWidth(130)
        self.btn_type_filter.clicked.connect(self.open_type_filter_dialog)
        
        web_bridge.start_stream.connect(self.remote_start)
        web_bridge.stop_stream.connect(self.remote_stop)
        web_bridge.clear_output.connect(self.clear_output_no_confirm)
        web_bridge.restart_app.connect(self.restart_application)

        self.setup_ui()
        self.check_autostart_web_server()
        
        if not self.config_exists:
            QTimer.singleShot(200, self.show_setup_wizard)

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        left_panel = QTabWidget()
        left_panel.setMaximumWidth(380)
        
        # --- TAB 1: Services ---
        services_tab = QWidget()
        s_layout = QVBoxLayout(services_tab)
        
        self.service_list = QListWidget()
        self.service_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.service_list.setDragDropMode(QAbstractItemView.NoDragDrop if self.data.get("sort_services_alpha", False) else QAbstractItemView.InternalMove)
        self.service_list.itemClicked.connect(self.load_service_to_form)
        self.service_list.itemSelectionChanged.connect(self.update_selectable_services)
        self.service_list.viewport().installEventFilter(self)
        
        form_layout = QFormLayout()
        self.form_layout = form_layout
        
        self.f_name = QLineEdit()
        
        self.f_stream_type = QComboBox()
        self.f_stream_type.addItem("Minisatip", "minisatip")
        self.f_stream_type.addItem("OpenWebif", "openwebif")
        self.f_stream_type.currentIndexChanged.connect(self.toggle_source_ui)
        
        self.f_owref = QLineEdit()
        self.f_owref.setPlaceholderText("e.g. 1:0:2:...")
        self.f_owref.textChanged.connect(self.on_owref_text_changed)
        
        self.f_src = QSpinBox()
        self.f_src.setRange(1, 256)
        self.f_src.setValue(1)
        
        self.f_freq = QLineEdit()
        
        self.f_pol = QComboBox()
        self.f_pol.addItem("Horizontal", "h")
        self.f_pol.addItem("Vertical", "v")
        
        self.f_sr = QLineEdit()
        
        self.f_msys = QComboBox()
        self.f_msys.addItem("DVB-S", "dvbs")
        self.f_msys.addItem("DVB-S2", "dvbs2")
        
        # Checkboxes for optional values
        self.f_mtype_en = QCheckBox("Mod Type:")
        self.f_mtype_en.setChecked(True)
        self.f_mtype = QComboBox()
        for t in ["QPSK", "8PSK", "16APSK", "32APSK", "64APSK", "128APSK", "256APSK"]:
            self.f_mtype.addItem(t, t.lower())
        self.f_mtype_en.stateChanged.connect(lambda: self.f_mtype.setEnabled(self.f_mtype_en.isChecked()))
            
        self.f_fec_en = QCheckBox("FEC:")
        self.f_fec_en.setChecked(True)
        self.f_fec = QComboBox()
        fecs = {"1/2":"12", "2/3":"23", "3/4":"34", "3/5":"35", "4/5":"45", "5/6":"56", "7/8":"78", "8/9":"89", "9/10":"910"}
        for k, v in fecs.items():
            self.f_fec.addItem(k, v)
        self.f_fec_en.stateChanged.connect(lambda: self.f_fec.setEnabled(self.f_fec_en.isChecked()))
        
        self.btn_url_pids = QPushButton("Configure [EXPERT]")
        self.btn_url_pids.clicked.connect(self.open_url_pids_dialog)
        
        self.f_uecp_source = QComboBox()
        self.f_uecp_source.addItem("Dedicated PID", "pid")
        self.f_uecp_source.addItem("Audio AAC", "aac")
        self.f_uecp_source.addItem("Audio MP2", "mp2")
        
        self.f_pid = QLineEdit()
        
        self.btn_ow_bouquet = QPushButton("Convert as Stations Bouquet")
        self.btn_ow_bouquet.clicked.connect(self.open_ow_bouquet_dialog)

        form_layout.addRow("Name:", self.f_name)
        form_layout.addRow("Stream Type:", self.f_stream_type)
        form_layout.addRow("OpenWebif Ref:", self.f_owref)
        form_layout.addRow("", self.btn_ow_bouquet)
        form_layout.addRow("Source (Tuner):", self.f_src)
        form_layout.addRow("Frequency:", self.f_freq)
        form_layout.addRow("Polarization:", self.f_pol)
        form_layout.addRow("Symbol Rate:", self.f_sr)
        form_layout.addRow("Mod System:", self.f_msys)
        form_layout.addRow(self.f_mtype_en, self.f_mtype)
        form_layout.addRow(self.f_fec_en, self.f_fec)
        form_layout.addRow("Minisatip PIDs:", self.btn_url_pids)
        form_layout.addRow("UECP Source:", self.f_uecp_source)
        form_layout.addRow("PID(s) to decode:", self.f_pid)
        
        self.btn_new = QPushButton("+ New Service")
        self.btn_new.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 4px 10px;")
        self.btn_new.clicked.connect(self.reset_form_to_new)

        new_btn_layout = QHBoxLayout()
        new_btn_layout.addWidget(self.btn_new)
        new_btn_layout.addStretch()

        btn_layout = QHBoxLayout()
        self.btn_save_new = QPushButton("Save as New Service")
        self.btn_update = QPushButton("Update Service")
        self.btn_del = QPushButton("Delete Service")
        
        self.btn_save_new.clicked.connect(self.add_new_service)
        self.btn_update.clicked.connect(self.update_service)
        self.btn_del.clicked.connect(self.delete_service)
        
        btn_layout.addWidget(self.btn_save_new)
        btn_layout.addWidget(self.btn_update)
        btn_layout.addWidget(self.btn_del)
        
        # Initial state at startup
        self.btn_save_new.setVisible(True)
        self.btn_update.setVisible(False)
        self.btn_del.setVisible(False)

        self.btn_connect = QPushButton("CONNECT TO STREAM")
        self.btn_connect.setFocusPolicy(Qt.NoFocus)
        self.btn_connect.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px; outline: none;")
        self.btn_connect.clicked.connect(self.toggle_connection)
        
        s_layout.addWidget(QLabel("Saved Services (Use Ctrl to select multiple):"))
        s_layout.addWidget(self.service_list)
        s_layout.addLayout(new_btn_layout)
        s_layout.addSpacing(5)
        s_layout.addLayout(form_layout)
        s_layout.addLayout(btn_layout)
        s_layout.addSpacing(10)
        s_layout.addWidget(self.btn_connect)

        # --- Checkboxes initialization at startup ---
        self.chk_blue_tech = QCheckBox("Display AF / CT / DI / DSN / MS / PTY / PI / PS in blue")
        self.chk_blue_tech.setChecked(self.data.get("blue_tech", True))
        self.chk_blue_tech.stateChanged.connect(self.save_disp_settings)

        self.chk_show_date = QCheckBox("Display date in Time column")
        self.chk_show_date.setChecked(self.data.get("show_date", False))
        self.chk_show_date.stateChanged.connect(self.save_disp_settings)

        self.chk_green_oda = QCheckBox("Display ODA / IH detections in green")
        self.chk_green_oda.setChecked(self.data.get("green_oda_ih", True))
        self.chk_green_oda.stateChanged.connect(self.save_disp_settings)

        self.chk_orange_os_ff = QCheckBox("Display OS / FF detections in orange")
        self.chk_orange_os_ff.setChecked(self.data.get("orange_os_ff", True))
        self.chk_orange_os_ff.stateChanged.connect(self.save_disp_settings)

        self.chk_pink_pi_ps = QCheckBox('Display TP / TA detections without TA enabled in pink')
        self.chk_pink_pi_ps.setChecked(self.data.get("pink_pi_ps", True))
        self.chk_pink_pi_ps.stateChanged.connect(self.save_disp_settings)

        self.chk_red_ta = QCheckBox('Display TP / TA detections with TA enabled (TP + TA ON) in red')
        self.chk_red_ta.setChecked(self.data.get("red_ta_on", True))
        self.chk_red_ta.stateChanged.connect(self.save_disp_settings)

        self.chk_purple_unknown = QCheckBox("Display unknown stations in purple")
        self.chk_purple_unknown.setChecked(self.data.get("purple_unknown", True))
        self.chk_purple_unknown.stateChanged.connect(self.save_disp_settings)

        self.chk_hide_addr_psn_audio = QCheckBox("Hide Address && PSN columns for MP2 / AAC streams")
        self.chk_hide_addr_psn_audio.setChecked(self.data.get("hide_addr_psn_audio", False))
        self.chk_hide_addr_psn_audio.stateChanged.connect(self.save_disp_settings)

        self.chk_hide_station_audio = QCheckBox("Hide Station column for MP2 / AAC streams")
        self.chk_hide_station_audio.setChecked(self.data.get("hide_station_audio", False))
        self.chk_hide_station_audio.stateChanged.connect(self.save_disp_settings)

        self.col_chks = []
        col_names = ["Time", "CRC", "Address", "PSN", "Station", "SQC", "Type", "Config", "Data"]
        hidden_cols = self.data.get("hidden_columns", [])
        for i, name in enumerate(col_names):
            chk = QCheckBox(name)
            chk.setChecked(i not in hidden_cols)
            chk.stateChanged.connect(self.update_col_visibility)
            self.col_chks.append(chk)

        self.disp_dialog = DisplaySettingsDialog(self)

        # --- TAB 2: Settings ---
        settings_tab = QWidget()
        srv_layout = QFormLayout(settings_tab)
        
        srv_layout.addRow(QLabel("<b>Receiver Source</b>"))
        self.srv_ip = QLineEdit(str(self.data.get("server_ip", "")))
        self.srv_port = QLineEdit(str(self.data.get("server_port", "8081")))
        self.ow_port = QLineEdit(str(self.data.get("openwebif_port", "8001")))
        srv_layout.addRow("Receiver IP:", self.srv_ip)
        srv_layout.addRow("Minisatip Port:", self.srv_port)
        srv_layout.addRow("OpenWebif Stream Port:", self.ow_port)
        
        srv_layout.addRow(QLabel("<b><br>Application Settings</b>"))
        self.max_rows_disabled_check = QCheckBox("Disable the Table Rows limit")
        self.max_rows_disabled_check.setChecked(self.data.get("max_rows_disabled", False))
        self.max_rows_warn_label = QLabel("Not setting a limit can result in high RAM usage!")
        self.max_rows_warn_label.setWordWrap(True)
        self.max_rows_warn_label.setStyleSheet("color: #444;")
        self.max_rows_input = QLineEdit(str(self.data.get("max_rows", 50000)))
        self.max_rows_input.setEnabled(not self.max_rows_disabled_check.isChecked())
        self.max_rows_disabled_check.stateChanged.connect(lambda: self.max_rows_input.setEnabled(not self.max_rows_disabled_check.isChecked()))
        srv_layout.addRow("Max Table Rows:", self.max_rows_input)
        srv_layout.addRow(self.max_rows_disabled_check)
        srv_layout.addRow(self.max_rows_warn_label)

        self.chk_auto_reconnect = QCheckBox("Auto-reconnect on stream loss (10s delay)")
        self.chk_auto_reconnect.setChecked(self.data.get("auto_reconnect", False))
        srv_layout.addRow(self.chk_auto_reconnect)

        self.chk_ow_auto_extract = QCheckBox("Auto-extract OpenWebif Ref from URL")
        self.chk_ow_auto_extract.setChecked(self.data.get("ow_auto_extract", True))
        srv_layout.addRow(self.chk_ow_auto_extract)

        srv_layout.addRow(QLabel("<b><br>Web Server Settings</b>"))
        self.web_checkbox = QCheckBox("Enable Web Server")
        self.web_checkbox.setChecked(self.data.get("web_enable", False))
        self.web_port = QLineEdit(str(self.data.get("web_port", "8090")))
        self.web_username = QLineEdit(str(self.data.get("web_username", "admin")))
        pass_layout = QHBoxLayout()
        self.web_password = QLineEdit(str(self.data.get("web_password", "admin")))
        self.web_password.setEchoMode(QLineEdit.Password)
        self.btn_show_pass = QPushButton("Show")
        self.btn_show_pass.setCheckable(True)
        self.btn_show_pass.toggled.connect(self.toggle_password_visibility)
        pass_layout.addWidget(self.web_password)
        pass_layout.addWidget(self.btn_show_pass)
        srv_layout.addRow(self.web_checkbox)
        srv_layout.addRow("Web Server Port:", self.web_port)
        srv_layout.addRow("Auth. Username:", self.web_username)
        srv_layout.addRow("Auth. Password:", pass_layout)

        srv_layout.addRow(QLabel("<b><br>Services & Display Management</b>"))
        self.chk_sort_alpha = QCheckBox("Sort services alphabetically")
        self.chk_sort_alpha.setChecked(self.data.get("sort_services_alpha", False))
        srv_layout.addRow(self.chk_sort_alpha)
        
        btn_open_disp = QPushButton("Display and Column Settings...")
        btn_open_disp.clicked.connect(self.disp_dialog.exec_)
        srv_layout.addRow(btn_open_disp)

        btn_restore = QPushButton("Restore Predefined Services")
        btn_restore.clicked.connect(self.restore_default_services)
        srv_layout.addRow(btn_restore)

        srv_layout.addRow(QLabel("<b><br>Apply Changes</b>"))
        btn_save_srv = QPushButton("Save Configuration")
        btn_save_srv.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")
        btn_save_srv.clicked.connect(self.save_server)
        srv_layout.addRow(btn_save_srv)

        # --- TAB 3: Address / PSN / PID Database ---
        db_tab = QWidget()
        db_layout = QVBoxLayout(db_tab)
        
        db_svc_sel = QFormLayout()
        self.a_svc_combo = QComboBox()
        self.a_svc_combo.currentTextChanged.connect(self.update_addr_table)
        db_svc_sel.addRow("Selected Service:", self.a_svc_combo)
        db_layout.addLayout(db_svc_sel)
        
        self.addr_table = QTableWidget(0, 3)
        self.addr_table.setHorizontalHeaderLabels(["Type", "Value", "Station Name"])
        self.addr_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.addr_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.addr_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.addr_table.verticalHeader().setVisible(False)
        self.addr_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.addr_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.addr_table.setSortingEnabled(True)
        self.addr_table.setTextElideMode(Qt.ElideRight)
        self.addr_table.setWordWrap(False)
        
        sort_col = self.data.get("db_sort_col", 0)
        sort_order = self.data.get("db_sort_order", 0)
        self.addr_table.horizontalHeader().setSortIndicator(sort_col, Qt.AscendingOrder if sort_order == 0 else Qt.DescendingOrder)
        self.addr_table.horizontalHeader().sortIndicatorChanged.connect(self.save_db_sort)
        
        self.addr_table.itemSelectionChanged.connect(self.on_db_row_selected)
        self.addr_table.itemChanged.connect(self.on_db_item_changed)
        
        a_form = QFormLayout()
        self.a_type = QComboBox()
        self.a_type.addItems(["Address", "PSN", "PID (for Minisatip)"])
        self.a_addr = QLineEdit()
        self.a_name = QLineEdit()
        a_form.addRow("Type:", self.a_type)
        a_form.addRow("Value:", self.a_addr)
        a_form.addRow("Station Name:", self.a_name)
        
        a_btns = QHBoxLayout()
        btn_add_addr = QPushButton("Add/Update")
        btn_del_addr = QPushButton("Delete")
        btn_add_addr.clicked.connect(self.add_address)
        btn_del_addr.clicked.connect(self.delete_address)
        a_btns.addWidget(btn_add_addr)
        a_btns.addWidget(btn_del_addr)
        
        db_layout.addWidget(self.addr_table)
        db_layout.addLayout(a_form)
        db_layout.addLayout(a_btns)
        
        left_panel.addTab(services_tab, "Services")
        left_panel.addTab(db_tab, "Address / PSN / PID Database")
        left_panel.addTab(settings_tab, "Settings")

        # --- RIGHT TABS ---
        self.right_tabs = QTabWidget()
        
        # TAB: Live Log
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        
        tools_layout = QHBoxLayout()
        btn_exp_txt = QPushButton("Export TXT")
        btn_exp_csv = QPushButton("Export CSV")
        btn_import = QPushButton("Import File")
        btn_copy_all = QPushButton("Copy All")
        
        btn_exp_txt.clicked.connect(self.export_txt)
        btn_exp_csv.clicked.connect(self.export_csv)
        btn_import.clicked.connect(self.import_file)
        btn_copy_all.clicked.connect(self.copy_all)
        
        tools_layout.addWidget(btn_exp_txt)
        tools_layout.addWidget(btn_exp_csv)
        tools_layout.addWidget(btn_import)
        tools_layout.addWidget(btn_copy_all)
        tools_layout.addStretch()
        
        self.msg_count_label = QLabel("Detections: 0")
        self.msg_count_label.setStyleSheet("font-weight: bold; margin-right: 15px;")
        tools_layout.addWidget(self.msg_count_label)
        
        btn_clear = QPushButton("Clear Output")
        btn_clear.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
        btn_clear.clicked.connect(self.clear_output)
        tools_layout.addWidget(btn_clear)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Address / Station:"))
        filter_layout.addWidget(self.filter_combo)
        
        filter_layout.addSpacing(15)
        filter_layout.addWidget(QLabel("PSN / Station:"))
        filter_layout.addWidget(self.filter_psn_combo)
        
        filter_layout.addSpacing(15)
        filter_layout.addWidget(QLabel("Type:"))
        filter_layout.addWidget(self.btn_type_filter)

        filter_layout.addSpacing(15)
        filter_layout.addWidget(QLabel("Search Config / Data:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Keyword...")
        self.search_input.setMinimumWidth(250)
        self.search_input.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.search_input)
        filter_layout.addStretch() 
        
        self.log_model = LogTableModel(self)
        self.log_table = QTableView()
        self.log_table.setModel(self.log_model)
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.log_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Stretch)
        self.log_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.log_table.verticalHeader().setDefaultSectionSize(60)
        self.log_table.setWordWrap(True)
        self.log_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.log_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.log_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.log_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.log_table.setSortingEnabled(True)
        self.log_table.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        
        # Restore saved column widths
        saved_widths = self.data.get("column_widths", [70, 40, 75, 40, 150, 40, 100, 180])
        for idx, w in enumerate(saved_widths):
            if idx < 8:
                self.log_table.setColumnWidth(idx, w)
        
        # Adjusts the Time width at startup if the date is enabled
        if self.data.get("show_date", False):
            self.log_table.setColumnWidth(0, max(self.log_table.columnWidth(0), 165))
        
        self.log_table.horizontalHeader().sectionResized.connect(self.save_column_widths)

        self.log_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log_table.customContextMenuRequested.connect(self.show_context_menu)

        self.highlight_delegate = HighlightDelegate(self.log_table)
        self.log_table.setItemDelegateForColumn(7, self.highlight_delegate)
        self.log_table.setItemDelegateForColumn(8, self.highlight_delegate)

        self.log_table.setStyleSheet("QTableView::item:selected { background-color: #e0e0e0; color: black; }")
        self.log_table.verticalScrollBar().valueChanged.connect(self.check_scroll_position)

        bottom_layout = QHBoxLayout()
        self.status_label = QLabel("Status: Disconnected.")
        
        self.btn_scroll_bottom = QPushButton("↓ Resume Live Scroll")
        self.btn_scroll_bottom.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 4px 10px;")
        self.btn_scroll_bottom.setVisible(False)
        self.btn_scroll_bottom.clicked.connect(self.force_scroll_bottom)
        
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_scroll_bottom)
        
        log_layout.addLayout(tools_layout)
        log_layout.addLayout(filter_layout)
        log_layout.addWidget(self.log_table)
        log_layout.addLayout(bottom_layout)
        
        # TAB: Grid View
        grid_tab = QWidget()
        grid_layout = QVBoxLayout(grid_tab)
        
        grid_tools_layout = QHBoxLayout()
        btn_exp_grid_txt = QPushButton("Export TXT")
        btn_exp_grid_csv = QPushButton("Export CSV")
        btn_copy_grid_all = QPushButton("Copy All")
        
        btn_exp_grid_txt.clicked.connect(self.export_grid_txt)
        btn_exp_grid_csv.clicked.connect(self.export_grid_csv)
        btn_copy_grid_all.clicked.connect(self.copy_grid_all)
        
        grid_tools_layout.addWidget(btn_exp_grid_txt)
        grid_tools_layout.addWidget(btn_exp_grid_csv)
        grid_tools_layout.addWidget(btn_copy_grid_all)
        grid_tools_layout.addStretch()
        btn_clear_grid = QPushButton("Clear Output")
        btn_clear_grid.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
        btn_clear_grid.clicked.connect(self.clear_output)
        grid_tools_layout.addWidget(btn_clear_grid)
        
        self.grid_table = QTableWidget(0, 3)
        self.grid_table.setHorizontalHeaderLabels(["Station", "Last Update", "Last Radiotext"])
        
        grid_widths = self.data.get("grid_column_widths", [150, 130])
        if len(grid_widths) >= 2:
            self.grid_table.setColumnWidth(0, grid_widths[0])
            self.grid_table.setColumnWidth(1, grid_widths[1])
            
        self.grid_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.grid_table.horizontalHeader().sectionResized.connect(self.save_grid_widths)
        
        self.grid_table.setAlternatingRowColors(True)
        self.grid_table.verticalHeader().setVisible(False)
        self.grid_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.grid_table.setSortingEnabled(True)
        self.grid_table.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        
        grid_layout.addLayout(grid_tools_layout)
        grid_layout.addWidget(self.grid_table)
        
        self.right_tabs.addTab(log_tab, "Full Monitoring")
        self.right_tabs.addTab(grid_tab, "Current Radiotext by station")
        
        layout.addWidget(left_panel)
        layout.addWidget(self.right_tabs)
        
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(self.search_input.setFocus)
        
        self.update_service_list()
        self.toggle_source_ui()
        self.update_type_filter_button()
        
        for i, chk in enumerate(self.col_chks):
            self.log_table.setColumnHidden(i, not chk.isChecked())

    def toggle_source_ui(self):
        is_ow = self.f_stream_type.currentData() == "openwebif"
        is_bouquet = is_ow and hasattr(self, 'current_ow_streams') and len(self.current_ow_streams) >= 2
        
        def set_row_visible(field, visible):
            field.setVisible(visible)
            label = self.form_layout.labelForField(field)
            if label:
                label.setVisible(visible)

        set_row_visible(self.f_owref, is_ow)
        set_row_visible(self.btn_ow_bouquet, is_ow)
        set_row_visible(self.f_src, not is_ow)
        set_row_visible(self.f_freq, not is_ow)
        set_row_visible(self.f_pol, not is_ow)
        set_row_visible(self.f_sr, not is_ow)
        set_row_visible(self.f_msys, not is_ow)
        set_row_visible(self.btn_url_pids, not is_ow)
        
        self.f_mtype_en.setVisible(not is_ow)
        self.f_mtype.setVisible(not is_ow)
        self.f_fec_en.setVisible(not is_ow)
        self.f_fec.setVisible(not is_ow)

        # Greys out individual fields if a group of 2 or more stations is configured
        self.f_owref.setEnabled(not is_bouquet)
        self.f_uecp_source.setEnabled(not is_bouquet)
        self.f_pid.setEnabled(not is_bouquet)

    def on_owref_text_changed(self, text):
        if self.data.get("ow_auto_extract", False) and "ref=" in text:
            match = re.search(r'ref=([^&]+)', text)
            if match:
                extracted = match.group(1).strip()
                if extracted != text:
                    self.f_owref.blockSignals(True)
                    self.f_owref.setText(extracted)
                    self.f_owref.blockSignals(False)

    def check_scroll_position(self):
        vbar = self.log_table.verticalScrollBar()
        is_at_bottom = vbar.value() >= vbar.maximum() - 2
        if self.active_threads and any(t.isRunning() for t in self.active_threads) and not is_at_bottom:
            self.btn_scroll_bottom.setVisible(True)
        else:
            self.btn_scroll_bottom.setVisible(False)

    def force_scroll_bottom(self):
        self.log_table.scrollToBottom()

    def on_db_row_selected(self):
        rows = self.addr_table.selectionModel().selectedRows()
        if rows:
            row = rows[0].row()
            row_type = self.addr_table.item(row, 0).text()
            if row_type == "PID":
                self.a_type.setCurrentText("PID (for Minisatip)")
            else:
                self.a_type.setCurrentText(row_type)
            self.a_addr.setText(self.addr_table.item(row, 1).text())
            self.a_name.setText(self.addr_table.item(row, 2).text())

    def on_db_item_changed(self, item):
        row = item.row()
        col = item.column()
        if col == 2:
            svc_name = self.a_svc_combo.currentText()
            type_item = self.addr_table.item(row, 0)
            val_item = self.addr_table.item(row, 1)
            if not type_item or not val_item: return
            
            b_type = type_item.text()
            val = val_item.text()
            new_name = item.text().strip()
            if not new_name: return
            
            for s in self.services:
                if s["name"] == svc_name:
                    book_key = "address_book" if b_type == "Address" else ("psn_book" if b_type == "PSN" else "pid_book")
                    if book_key in s and val in s[book_key]:
                        s[book_key][val] = new_name
                        self.save_services()
                        self.update_active_books(svc_name)
                    break

    def save_db_widths(self, logicalIndex, oldSize, newSize):
        self.data["db_column_widths"] = [self.addr_table.columnWidth(0), self.addr_table.columnWidth(1)]
        self.save_config()

    def save_db_sort(self, logicalIndex, order):
        self.data["db_sort_col"] = logicalIndex
        self.data["db_sort_order"] = 0 if order == Qt.AscendingOrder else 1
        self.save_config()

    def update_addr_table(self):
        if not hasattr(self, 'a_svc_combo'): return
        svc_name = self.a_svc_combo.currentText()
        self.addr_table.blockSignals(True)
        self.addr_table.setSortingEnabled(False)
        self.addr_table.setRowCount(0)
        if not svc_name: 
            self.addr_table.setSortingEnabled(True)
            self.addr_table.blockSignals(False)
            return
        
        for s in self.services:
            if s["name"] == svc_name:
                a_book = s.get("address_book", {})
                p_book = s.get("psn_book", {})
                pid_book = s.get("pid_book", {})
                
                for addr, name in a_book.items():
                    row = self.addr_table.rowCount()
                    self.addr_table.insertRow(row)
                    item_type = QTableWidgetItem("Address")
                    item_type.setFlags(item_type.flags() & ~Qt.ItemIsEditable)
                    item_val = NumericTableWidgetItem(addr)
                    item_val.setFlags(item_val.flags() & ~Qt.ItemIsEditable)
                    item_name = QTableWidgetItem(name)
                    item_name.setToolTip(name)
                    self.addr_table.setItem(row, 0, item_type)
                    self.addr_table.setItem(row, 1, item_val)
                    self.addr_table.setItem(row, 2, item_name)
                    
                for psn, name in p_book.items():
                    row = self.addr_table.rowCount()
                    self.addr_table.insertRow(row)
                    item_type = QTableWidgetItem("PSN")
                    item_type.setFlags(item_type.flags() & ~Qt.ItemIsEditable)
                    item_val = NumericTableWidgetItem(psn)
                    item_val.setFlags(item_val.flags() & ~Qt.ItemIsEditable)
                    item_name = QTableWidgetItem(name)
                    item_name.setToolTip(name)
                    self.addr_table.setItem(row, 0, item_type)
                    self.addr_table.setItem(row, 1, item_val)
                    self.addr_table.setItem(row, 2, item_name)

                for pid_val, name in pid_book.items():
                    row = self.addr_table.rowCount()
                    self.addr_table.insertRow(row)
                    item_type = QTableWidgetItem("PID")
                    item_type.setFlags(item_type.flags() & ~Qt.ItemIsEditable)
                    item_val = NumericTableWidgetItem(pid_val)
                    item_val.setFlags(item_val.flags() & ~Qt.ItemIsEditable)
                    item_name = QTableWidgetItem(name)
                    item_name.setToolTip(name)
                    self.addr_table.setItem(row, 0, item_type)
                    self.addr_table.setItem(row, 1, item_val)
                    self.addr_table.setItem(row, 2, item_name)
                break
        self.addr_table.setSortingEnabled(True)
        self.addr_table.blockSignals(False)

    def add_address(self):
        svc_name = self.a_svc_combo.currentText()
        if not svc_name: return
        b_type = self.a_type.currentText()
        val = self.a_addr.text().strip()
        name = self.a_name.text().strip()
        if val and name:
            if b_type == "Address":
                book_key = "address_book"
            elif b_type == "PSN":
                book_key = "psn_book"
            else:
                book_key = "pid_book"

            for s in self.services:
                if s["name"] == svc_name:
                    if book_key not in s:
                        s[book_key] = {}
                    if val in s[book_key]:
                        existing = s[book_key][val]
                        type_name = "PID" if "PID" in b_type else b_type
                        reply = QMessageBox.question(self, "Overwrite Database", 
                            f"The {type_name} '{val}' is already assigned to '{existing}' in service '{svc_name}'.\n"
                            f"Saving this will overwrite it with '{name}'.\n\nDo you want to continue?",
                            QMessageBox.Yes | QMessageBox.No)
                        if reply == QMessageBox.No:
                            return
                    s[book_key][val] = name
                    self.save_services()
                    self.update_addr_table()
                    self.update_active_books(svc_name)
                    self.a_addr.clear()
                    self.a_name.clear()
                    break

    def delete_address(self):
        svc_name = self.a_svc_combo.currentText()
        if not svc_name: return
        rows = self.addr_table.selectionModel().selectedRows()
        if not rows: return
        
        if len(rows) == 1:
            row = rows[0].row()
            b_type = self.addr_table.item(row, 0).text()
            val = self.addr_table.item(row, 1).text()
            name = self.addr_table.item(row, 2).text()
            msg = f"Are you sure you want to delete {b_type} '{val}' ({name}) from service '{svc_name}'?"
        else:
            msg = f"Are you sure you want to delete {len(rows)} entries from service '{svc_name}'?"
            
        reply = QMessageBox.question(
            self, 
            "Delete Entries", 
            msg, 
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
            
        for s in self.services:
            if s["name"] == svc_name:
                for model_index in sorted(rows, key=lambda x: x.row(), reverse=True):
                    row = model_index.row()
                    b_type = self.addr_table.item(row, 0).text()
                    val = self.addr_table.item(row, 1).text()
                    book_key = "address_book" if b_type == "Address" else ("psn_book" if b_type == "PSN" else "pid_book")
                    if book_key in s and val in s[book_key]:
                        del s[book_key][val]
                
                self.save_services()
                self.update_addr_table()
                self.update_active_books(svc_name)
                break

    def open_url_pids_dialog(self):
        dlg = UrlPidsDialog(self.current_url_pids, self)
        if dlg.exec_() == QDialog.Accepted:
            self.current_url_pids = dlg.get_value()

    def open_ow_bouquet_dialog(self):
        if not hasattr(self, 'current_ow_streams') or not self.current_ow_streams:
            self.current_ow_streams = [{}]
        if not self.current_ow_streams[0].get("name"):
            self.current_ow_streams[0]["name"] = self.f_name.text().strip()
        self.current_ow_streams[0]["ref"] = self.f_owref.text().strip()
        self.current_ow_streams[0]["uecp_source"] = self.f_uecp_source.currentData()
        self.current_ow_streams[0]["pid"] = self.f_pid.text().strip()
        
        dlg = OpenWebifBouquetDialog(self.current_ow_streams, self)
        if dlg.exec_() == QDialog.Accepted:
            new_streams = dlg.get_streams()
            if new_streams:
                self.current_ow_streams = new_streams
                first = self.current_ow_streams[0]
                self.f_owref.setText(first.get("ref", ""))
                idx = self.f_uecp_source.findData(first.get("uecp_source", "pid"))
                if idx >= 0: self.f_uecp_source.setCurrentIndex(idx)
                self.f_pid.setText(first.get("pid", ""))
                count = len(self.current_ow_streams)
                if count >= 2:
                    self.btn_ow_bouquet.setText(f"Manage Stations Bouquet ({count} streams)")
                else:
                    self.btn_ow_bouquet.setText("Convert as Stations Bouquet")
                self.toggle_source_ui()
                
                # Automatic update and saving of the service
                if self.editing_service_name:
                    new_svc = self.get_form_service_data()
                    if new_svc:
                        idx = next((i for i, s in enumerate(self.services) if s["name"] == self.editing_service_name), None)
                        if idx is not None:
                            new_svc["address_book"] = self.services[idx].get("address_book", {})
                            new_svc["psn_book"] = self.services[idx].get("psn_book", {})
                            self.services[idx] = new_svc
                            self.save_services()
                            self.update_active_books(self.editing_service_name)

    def toggle_password_visibility(self, checked):
        if checked:
            self.web_password.setEchoMode(QLineEdit.Normal)
            self.btn_show_pass.setText("Hide")
        else:
            self.web_password.setEchoMode(QLineEdit.Password)
            self.btn_show_pass.setText("Show")

    def show_context_menu(self, pos):
        index = self.log_table.indexAt(pos)
        if not index.isValid(): return
        row = index.row()
        if row >= len(self.log_model._filtered_rows): return
        row_data = self.log_model._filtered_rows[row]
        station = row_data.get("station", "")
        
        if station != "Unknown": return
        
        addr = row_data.get("address", "")
        psn = row_data.get("psn", "")
        
        menu = QMenu(self)
        action_addr = menu.addAction(f"Add Address ({addr}) to Database") if addr and addr != "0" else None
        action_psn = menu.addAction(f"Add PSN ({psn}) to Database") if psn else None
        
        if not action_addr and not action_psn: return
        
        action = menu.exec_(self.log_table.mapToGlobal(pos))
        if action_addr and action == action_addr:
            self.prompt_add_to_db("Address", addr)
        elif action_psn and action == action_psn:
            self.prompt_add_to_db("PSN", psn)
            
    def prompt_add_to_db(self, b_type, val):
        selected_items = self.service_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "No service selected.\nPlease select a service first to add to its database.")
            return
            
        svc_name = selected_items[0].text().replace("→ ", "")
            
        name, ok = QInputDialog.getText(self, f"Add {b_type}", f"Enter Station Name for {b_type} '{val}':")
        if ok and name:
            name = name.strip()
            for s in self.services:
                if s["name"] == svc_name:
                    book_key = "address_book" if b_type == "Address" else "psn_book"
                    if book_key not in s: s[book_key] = {}
                    
                    if val in s[book_key]:
                        existing = s[book_key][val]
                        reply = QMessageBox.question(self, "Overwrite Database", 
                            f"The {b_type} '{val}' is already assigned to '{existing}' in service '{svc_name}'.\n"
                            f"Saving this will overwrite it with '{name}'.\n\nDo you want to continue?",
                            QMessageBox.Yes | QMessageBox.No)
                        if reply == QMessageBox.No:
                            return

                    s[book_key][val] = name
                    self.save_services()
                    self.update_active_books([i.text() for i in self.service_list.selectedItems()])
                    break

    # --- Display Settings Logic ---
    def save_disp_settings(self):
        self.data["show_date"] = self.chk_show_date.isChecked()
        self.data["green_oda_ih"] = self.chk_green_oda.isChecked()
        self.data["red_ta_on"] = self.chk_red_ta.isChecked()
        self.data["purple_unknown"] = self.chk_purple_unknown.isChecked()
        self.data["blue_tech"] = self.chk_blue_tech.isChecked()
        self.data["orange_os_ff"] = self.chk_orange_os_ff.isChecked()
        self.data["pink_pi_ps"] = self.chk_pink_pi_ps.isChecked()
        self.data["hide_addr_psn_audio"] = self.chk_hide_addr_psn_audio.isChecked()
        self.data["hide_station_audio"] = self.chk_hide_station_audio.isChecked()
        
        global shared_show_date
        global shared_green_oda
        global shared_red_ta
        global shared_purple_unknown
        global shared_blue_tech
        global shared_orange_os_ff
        global shared_pink_pi_ps
        shared_show_date = self.chk_show_date.isChecked()
        shared_green_oda = self.chk_green_oda.isChecked()
        shared_red_ta = self.chk_red_ta.isChecked()
        shared_purple_unknown = self.chk_purple_unknown.isChecked()
        shared_blue_tech = self.chk_blue_tech.isChecked()
        shared_orange_os_ff = self.chk_orange_os_ff.isChecked()
        shared_pink_pi_ps = self.chk_pink_pi_ps.isChecked()
        
        # Automatic adjustment of the Time column width if the date is displayed
        if self.chk_show_date.isChecked():
            self.log_table.setColumnWidth(0, 165)
        else:
            self.log_table.setColumnWidth(0, 70)
        
        self.save_config()
        self.refresh_table_colors()
        self.refresh_time_format()
        self.update_col_visibility()

    def refresh_time_format(self):
        # 1. Instant update of the virtual model
        if hasattr(self, 'log_model'):
            self.log_model.beginResetModel()
            self.log_model.endResetModel()

        # 2. Grid View update
        self.grid_table.setSortingEnabled(False)
        for row in range(self.grid_table.rowCount()):
            item = self.grid_table.item(row, 1)
            if item:
                ts = item.data(Qt.UserRole)
                if ts is not None and ts != 0:
                    try:
                        dt = datetime.fromtimestamp(float(ts))
                        item.setText(dt.strftime('%d/%m/%Y %H:%M:%S') if self.chk_show_date.isChecked() else dt.strftime('%H:%M:%S'))
                    except Exception:
                        if not self.chk_show_date.isChecked():
                            item.setText(item.text().split(" ")[-1])
                else:
                    if not self.chk_show_date.isChecked():
                        item.setText(item.text().split(" ")[-1])
            self.grid_table.setSortingEnabled(True)

    def update_col_visibility(self):
        hidden = []
        
        # Detects whether the current or selected stream is an audio stream (MP2 or AAC)
        is_audio = False
        if self.active_threads and any(t.isRunning() for t in self.active_threads):
            is_audio = any(getattr(t, 'uecp_source', 'pid') in ['mp2', 'aac'] for t in self.active_threads)
        else:
            is_audio = self.f_uecp_source.currentData() in ['mp2', 'aac']

        hide_addr_psn = self.data.get("hide_addr_psn_audio", False) and is_audio
        hide_station = self.data.get("hide_station_audio", False) and is_audio

        for i, chk in enumerate(self.col_chks):
            is_hidden = not chk.isChecked()
            if hide_addr_psn and i in (2, 3):  # Address and PSN columns
                is_hidden = True
            if hide_station and i == 4:        # Station column
                is_hidden = True
            self.log_table.setColumnHidden(i, is_hidden)
            if is_hidden: 
                hidden.append(i)
        self.data["hidden_columns"] = hidden
        global shared_hidden_cols
        shared_hidden_cols = hidden
        self.save_config()

    def refresh_table_colors(self):
        if hasattr(self, 'log_model'):
            self.log_model.beginResetModel()
            self.log_model.endResetModel()

    # --- File Data Persistence ---
    def save_column_widths(self, logicalIndex, oldSize, newSize):
        widths = [self.log_table.columnWidth(i) for i in range(8)]
        self.data["column_widths"] = widths
        self.save_config()

    def save_grid_widths(self, logicalIndex, oldSize, newSize):
        widths = [self.grid_table.columnWidth(0), self.grid_table.columnWidth(1)]
        self.data["grid_column_widths"] = widths
        self.save_config()

    def load_config(self):
        try:
            with open(self.config_file, "r") as f:
                self.data.update(json.load(f))
        except Exception:
            pass

    def save_config(self):
        global shared_settings_full
        shared_settings_full = self.data
        temp_data = self.data.copy()
        if "services" in temp_data:
            del temp_data["services"]
        with open(self.config_file, "w") as f:
            json.dump(temp_data, f, indent=4)

    def load_services(self):
        import copy
        try:
            with open("services_custom.json", "r", encoding="utf-8") as f:
                self.services = json.load(f)
        except Exception:
            self.services = copy.deepcopy(DEFAULT_SERVICES)
            self.save_services()
            return

        custom_names = {s["name"]: s for s in self.services}
        changed = False

        for ds in DEFAULT_SERVICES:
            if ds["name"] not in custom_names:
                self.services.append(copy.deepcopy(ds))
                changed = True
            else:
                cs = custom_names[ds["name"]]
                
                if "address_book" not in cs: cs["address_book"] = {}
                for addr, name in ds["address_book"].items():
                    if cs["address_book"].get(addr) != name:
                        cs["address_book"][addr] = name
                        changed = True
                        
                if "psn_book" not in cs: cs["psn_book"] = {}
                for psn, name in ds["psn_book"].items():
                    if cs["psn_book"].get(psn) != name:
                        cs["psn_book"][psn] = name
                        changed = True
        
        if changed:
            self.save_services()
            
        if self.data.get("sort_services_alpha", False):
            self.services.sort(key=lambda x: x["name"].lower())

    def save_services(self):
        global shared_services_full
        shared_services_full = self.services
        with open("services_custom.json", "w", encoding="utf-8") as f:
            json.dump(self.services, f, indent=4)

    def restore_default_services(self):
        reply = QMessageBox.question(self, "Restore Defaults", 
                                     "The predefined services will be restored to their default settings.\n"
                                     "Your custom services will not be affected.\n"
                                     "Do you want to continue?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                with open("services_default.json", "r", encoding="utf-8") as f:
                    defaults = json.load(f)
                
                default_names = {s["name"] for s in defaults}
                custom_services = [s for s in self.services if s["name"] not in default_names]
                
                self.services = custom_services + defaults
                if self.data.get("sort_services_alpha", False):
                    self.services.sort(key=lambda x: x["name"].lower())
                
                self.save_services()
                self.update_service_list()
                QMessageBox.information(self, "Restored", "Predefined services have been restored.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to restore defaults.\n\nError details:\n{e}")

    # --- Server logic ---
    def save_server(self):
        restart_needed = False
        
        new_ip = self.srv_ip.text()
        new_port = self.srv_port.text()
        new_ow_port = self.ow_port.text()
        new_web_en = self.web_checkbox.isChecked()
        new_web_port = self.web_port.text()
        new_web_user = self.web_username.text()
        new_web_pass = self.web_password.text()
        new_sort_alpha = self.chk_sort_alpha.isChecked()
        new_max_dis = self.max_rows_disabled_check.isChecked()
        new_auto_reconnect = self.chk_auto_reconnect.isChecked()
        new_ow_auto_extract = self.chk_ow_auto_extract.isChecked()
        try:
            new_max = int(self.max_rows_input.text())
        except ValueError:
            new_max = 50000
            
        if (self.data.get("server_ip") != new_ip or
            self.data.get("server_port") != new_port or
            self.data.get("openwebif_port") != new_ow_port or
            self.data.get("web_enable") != new_web_en or
            self.data.get("web_port") != new_web_port or
            self.data.get("web_username") != new_web_user or
            self.data.get("web_password") != new_web_pass or
            self.data.get("max_rows") != new_max or
            self.data.get("max_rows_disabled") != new_max_dis or
            self.data.get("auto_reconnect") != new_auto_reconnect or
            self.data.get("ow_auto_extract") != new_ow_auto_extract):
            restart_needed = True

        self.data["server_ip"] = new_ip
        self.data["server_port"] = new_port
        self.data["openwebif_port"] = new_ow_port
        self.data["web_enable"] = new_web_en
        self.data["web_port"] = new_web_port
        self.data["web_username"] = new_web_user
        self.data["web_password"] = new_web_pass
        self.data["sort_services_alpha"] = new_sort_alpha
        self.data["max_rows"] = new_max
        self.data["max_rows_disabled"] = new_max_dis
        self.data["auto_reconnect"] = new_auto_reconnect
        self.data["ow_auto_extract"] = new_ow_auto_extract
        
        if new_sort_alpha:
            self.services.sort(key=lambda x: x["name"].lower())
            self.service_list.setDragDropMode(QAbstractItemView.NoDragDrop)
            self.save_services()
            self.update_service_list()
        else:
            self.service_list.setDragDropMode(QAbstractItemView.InternalMove)
        
        global shared_web_username
        global shared_web_password
        shared_web_username = new_web_user
        shared_web_password = new_web_pass
        
        self.save_config()
        
        global shared_messages
        new_len = None if new_max_dis else new_max
        if shared_messages.maxlen != new_len:
            shared_messages = deque(shared_messages, maxlen=new_len)
            
        if restart_needed:
            QMessageBox.information(self, "Saved", "Configuration saved successfully.\nYou must restart the software to apply all changes.")
        else:
            QMessageBox.information(self, "Saved", "Configuration saved successfully.")
            
        self.check_autostart_web_server()

    def check_autostart_web_server(self):
        if self.data.get("web_enable", False) and self.flask_thread is None:
            port = int(self.data.get("web_port", "5000"))
            self.flask_thread = threading.Thread(target=run_flask_app, args=(port,), daemon=True)
            self.flask_thread.start()

    def update_service_list(self):
        self.service_list.clear()
        
        global shared_services
        shared_services.clear()
        
        if hasattr(self, 'a_svc_combo'):
            curr_db_svc = self.a_svc_combo.currentText()
            self.a_svc_combo.blockSignals(True)
            self.a_svc_combo.clear()
        
        for s in self.services:
            self.service_list.addItem(s["name"])
            shared_services.append(s["name"])
            if hasattr(self, 'a_svc_combo'):
                self.a_svc_combo.addItem(s["name"])
                
        if hasattr(self, 'a_svc_combo'):
            idx = self.a_svc_combo.findText(curr_db_svc)
            if idx >= 0: self.a_svc_combo.setCurrentIndex(idx)
            self.a_svc_combo.blockSignals(False)
            self.update_addr_table()

    def get_service_stream_type(self, name):
        for s in self.services:
            if s["name"] == name:
                return s.get("stream_type", "minisatip")
        return "minisatip"

    def get_service_owref(self, name):
        for s in self.services:
            if s["name"] == name:
                return s.get("ow_ref", "")
        return ""

    def get_service_tp(self, name):
        for s in self.services:
            if s["name"] == name:
                return (
                    s.get("src", 1),
                    s.get("freq", ""),
                    s.get("pol", "h"),
                    s.get("sr", ""),
                    s.get("msys", "dvbs2"),
                    s.get("mtype_en", True),
                    s.get("mtype", "qpsk"),
                    s.get("fec_en", True),
                    s.get("fec", "34")
                )
        return None

    def eventFilter(self, source, event):
        # Blocks clicks in the empty space of the list to prevent accidental deselection, and captures drag-and-drop operations
        if hasattr(self, 'service_list') and source == self.service_list.viewport():
            if event.type() == QEvent.MouseButtonPress:
                if not self.service_list.itemAt(event.pos()):
                    return True
            elif event.type() == QEvent.Drop:
                QTimer.singleShot(0, self.on_services_reordered)
        return super().eventFilter(source, event)

    def on_services_reordered(self):
        new_order = [self.service_list.item(i).text().replace("→ ", "") for i in range(self.service_list.count())]
        service_dict = {s["name"]: s for s in self.services}
        self.services = [service_dict[name] for name in new_order if name in service_dict]
        self.save_services()
        self.update_selectable_services()

    def update_selectable_services(self):
        selected_items = self.service_list.selectedItems()
        current_selected_names = [i.text().replace("→ ", "") for i in selected_items]
        
        # Detection of any change in selection (change of service or deselection)
        if hasattr(self, 'prev_selected_names') and self.prev_selected_names:
            if set(current_selected_names) != set(self.prev_selected_names):
                # If the command originates from the web server, the blocking pop-up is bypassed
                if getattr(self, 'bypass_change_confirmation', False):
                    if self.active_threads and any(t.isRunning() for t in self.active_threads):
                        self.toggle_connection()
                    self.clear_output_no_confirm()
                elif self.log_model.rowCount() > 0 or (self.active_threads and any(t.isRunning() for t in self.active_threads)):
                    reply = QMessageBox.question(
                        self, 
                        "Change Service", 
                        "Switching to another service will erase decoded data and interrupt the current stream.\nDo you want to continue?", 
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.No:
                        # Immediately restores the previous selection
                        self.service_list.blockSignals(True)
                        for i in range(self.service_list.count()):
                            item = self.service_list.item(i)
                            raw_name = item.text().replace("→ ", "")
                            item.setSelected(raw_name in self.prev_selected_names)
                        self.service_list.blockSignals(False)
                        return

                    # Upon 'Yes' confirmation, the stream stops and resets
                    if self.active_threads and any(t.isRunning() for t in self.active_threads):
                        self.toggle_connection()
                    self.clear_output_no_confirm()

        # If the user has deselected all services
        if not selected_items:
            self.prev_selected_names = []
            self.service_list.blockSignals(True)
            for i in range(self.service_list.count()):
                item = self.service_list.item(i)
                item.setText(item.text().replace("→ ", ""))
                item.setForeground(QColor("#000000"))
                item.setBackground(QColor(Qt.transparent))
            self.service_list.blockSignals(False)
            return

        # If the user makes a multiple selection, the transponder compatibility is checked
        first_svc_name = selected_items[0].text().replace("→ ", "")
        first_stream_type = self.get_service_stream_type(first_svc_name)
        is_ow = first_stream_type == "openwebif"
        
        if is_ow:
            first_match = self.get_service_owref(first_svc_name)
        else:
            first_match = self.get_service_tp(first_svc_name)

        if len(selected_items) > 1:
            for item in selected_items[1:]:
                item_name = item.text().replace("→ ", "")
                item_type = self.get_service_stream_type(item_name)
                
                if item_type != first_stream_type:
                    self.service_list.blockSignals(True)
                    item.setSelected(False)
                    self.service_list.blockSignals(False)
                    continue
                    
                match_val = self.get_service_owref(item_name) if is_ow else self.get_service_tp(item_name)
                if match_val != first_match:
                    # Incompatibility case: the incompatible item is automatically deselected
                    self.service_list.blockSignals(True)
                    item.setSelected(False)
                    self.service_list.blockSignals(False)

        valid_selected = self.service_list.selectedItems()
        if not valid_selected: return
        
        first_svc_name = valid_selected[0].text().replace("→ ", "")
        first_stream_type = self.get_service_stream_type(first_svc_name)
        is_ow = first_stream_type == "openwebif"
        
        if is_ow:
            first_match = self.get_service_owref(first_svc_name)
        else:
            first_match = self.get_service_tp(first_svc_name)

        # Application of the arrow to the companion services of the same transponder
        self.service_list.blockSignals(True)
        for i in range(self.service_list.count()):
            item = self.service_list.item(i)
            raw_name = item.text().replace("→ ", "")
            item_type = self.get_service_stream_type(raw_name)
            match_val = self.get_service_owref(raw_name) if item_type == "openwebif" else self.get_service_tp(raw_name)
            
            item.setBackground(QColor(Qt.transparent))
            if item_type == first_stream_type and match_val == first_match and match_val:
                if raw_name != first_svc_name:
                    item.setText(f"→ {raw_name}")
                else:
                    item.setText(raw_name)
            else:
                item.setText(raw_name)
        self.service_list.blockSignals(False)

        selected_names = [i.text().replace("→ ", "") for i in valid_selected]
        self.prev_selected_names = selected_names
        self.update_active_books(selected_names)

        if len(valid_selected) == 1:
            self.load_service_to_form(valid_selected[0])

    def load_service_to_form(self, item):
        name = item.text().replace("→ ", "")
        
        # Updates the fields only if the element is indeed part of the validated selection
        if hasattr(self, 'prev_selected_names') and self.prev_selected_names and name not in self.prev_selected_names:
            return
            
        self.editing_service_name = name
        
        for s in self.services:
            if s["name"] == name:
                self.f_name.setText(s["name"])
                
                stream_type = s.get("stream_type", "minisatip")
                idx = self.f_stream_type.findData(stream_type)
                if idx >= 0: self.f_stream_type.setCurrentIndex(idx)
                
                self.f_src.setValue(int(s.get("src", 1)))
                self.f_freq.setText(s.get("freq", ""))
                
                idx = self.f_pol.findData(s.get("pol", "h"))
                if idx >= 0: self.f_pol.setCurrentIndex(idx)
                
                self.f_sr.setText(s.get("sr", ""))
                
                idx = self.f_msys.findData(s.get("msys", "dvbs2"))
                if idx >= 0: self.f_msys.setCurrentIndex(idx)
                
                self.f_mtype_en.setChecked(s.get("mtype_en", True))
                idx = self.f_mtype.findData(s.get("mtype", "qpsk"))
                if idx >= 0: self.f_mtype.setCurrentIndex(idx)
                
                self.f_fec_en.setChecked(s.get("fec_en", True))
                idx = self.f_fec.findData(s.get("fec", "34"))
                if idx >= 0: self.f_fec.setCurrentIndex(idx)
                
                self.current_url_pids = s.get("url_pids", "all")
                
                ow_streams = s.get("ow_streams", [])
                self.current_ow_streams = [dict(st) for st in ow_streams]
                if not self.current_ow_streams:
                    self.current_ow_streams = [{
                        "name": s.get("name", ""),
                        "ref": s.get("ow_ref", ""),
                        "uecp_source": s.get("uecp_source", "pid"),
                        "pid": s.get("pid", "")
                    }]
                
                first = self.current_ow_streams[0]
                self.f_owref.setText(first.get("ref", ""))
                idx = self.f_uecp_source.findData(first.get("uecp_source", "pid"))
                if idx >= 0: self.f_uecp_source.setCurrentIndex(idx)
                self.f_pid.setText(first.get("pid", ""))
                
                count = len(self.current_ow_streams)
                if count >= 2:
                    self.btn_ow_bouquet.setText(f"Manage Stations Bouquet ({count} streams)")
                else:
                    self.btn_ow_bouquet.setText("Convert as Stations Bouquet")
                
                # Immediate synchronization of the Address / PSN / PID Database tab
                if hasattr(self, 'a_svc_combo'):
                    idx_db = self.a_svc_combo.findText(name)
                    if idx_db >= 0:
                        self.a_svc_combo.setCurrentIndex(idx_db)
                
                # Switch to edit mode: display Update and Delete at the bottom
                self.btn_save_new.setVisible(False)
                self.btn_update.setVisible(True)
                self.btn_del.setVisible(True)
                
                self.toggle_source_ui()
                self.update_col_visibility()
                break

    def get_form_service_data(self):
        name = self.f_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Service name cannot be empty.\nPlease check your configuration.")
            return None
            
        if not hasattr(self, 'current_ow_streams') or not self.current_ow_streams:
            self.current_ow_streams = [{}]
        if not self.current_ow_streams[0].get("name"):
            self.current_ow_streams[0]["name"] = name
        self.current_ow_streams[0]["ref"] = self.f_owref.text().strip()
        self.current_ow_streams[0]["uecp_source"] = self.f_uecp_source.currentData()
        self.current_ow_streams[0]["pid"] = self.f_pid.text().strip()
            
        return {
            "name": name, 
            "stream_type": self.f_stream_type.currentData(),
            "ow_ref": self.f_owref.text().strip(),
            "src": self.f_src.value(), 
            "freq": self.f_freq.text(),
            "pol": self.f_pol.currentData(), 
            "sr": self.f_sr.text(), 
            "msys": self.f_msys.currentData(),
            "mtype_en": self.f_mtype_en.isChecked(),
            "mtype": self.f_mtype.currentData(), 
            "fec_en": self.f_fec_en.isChecked(),
            "fec": self.f_fec.currentData(), 
            "url_pids": self.current_url_pids,
            "uecp_source": self.f_uecp_source.currentData(),
            "pid": self.f_pid.text(),
            "ow_streams": self.current_ow_streams
        }

    def reset_form_to_new(self):
        """Completely resets the form to create a new blank service from scratch."""
        self.service_list.clearSelection()
        self.editing_service_name = ""
        self.f_name.clear()
        self.f_stream_type.setCurrentIndex(0)
        self.f_owref.clear()
        self.f_src.setValue(1)
        self.f_freq.clear()
        self.f_pol.setCurrentIndex(0)
        self.f_sr.clear()
        self.f_msys.setCurrentIndex(1)
        self.f_mtype_en.setChecked(True)
        self.f_mtype.setCurrentIndex(0)
        self.f_fec_en.setChecked(True)
        self.f_fec.setCurrentIndex(2)
        self.current_url_pids = "all"
        self.f_uecp_source.setCurrentIndex(0)
        self.f_pid.clear()
        self.current_ow_streams = []
        self.btn_ow_bouquet.setText("Convert as Stations Bouquet")
        
        # Switch to creation mode: only Save New Service is visible at the bottom
        self.btn_save_new.setVisible(True)
        self.btn_update.setVisible(False)
        self.btn_del.setVisible(False)
        
        self.toggle_source_ui()
        self.update_col_visibility()

    def add_new_service(self):
        new_svc = self.get_form_service_data()
        if not new_svc: return
        
        name = new_svc["name"]
        if any(s["name"] == name for s in self.services):
            QMessageBox.warning(self, "Error", f"A service named '{name}' already exists.\nPlease use 'Update' to modify it or choose another name.")
            return
            
        new_svc["address_book"] = {}
        new_svc["psn_book"] = {}
        self.services.append(new_svc)
        self.editing_service_name = name
        
        if self.data.get("sort_services_alpha", False):
            self.services.sort(key=lambda x: x["name"].lower())
            
        self.save_services()
        self.update_service_list()
        
        # Automatic selection of the newly added service (which switches the buttons to Update/Delete)
        items = self.service_list.findItems(name, Qt.MatchExactly)
        if items:
            self.service_list.clearSelection()
            items[0].setSelected(True)
            self.load_service_to_form(items[0])
            
        QMessageBox.information(self, "Success", f"Service '{name}' added successfully.")

    def update_service(self):
        if not self.editing_service_name:
            QMessageBox.warning(self, "Error", "Please select a service from the list first to update it.")
            return
            
        old_idx = next((i for i, s in enumerate(self.services) if s["name"] == self.editing_service_name), None)
        if old_idx is None:
            QMessageBox.warning(self, "Error", "The selected service could not be found.")
            return
            
        new_svc = self.get_form_service_data()
        if not new_svc: return
        
        name = new_svc["name"]
        existing_idx = next((i for i, s in enumerate(self.services) if s["name"] == name), None)
        if existing_idx is not None and existing_idx != old_idx:
            QMessageBox.warning(self, "Error", f"Another service named '{name}' already exists. Please choose a different name.")
            return
            
        reply = QMessageBox.question(
            self,
            "Update Service",
            f"Are you sure you want to update service '{self.editing_service_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
            
        # Systematic retention of databases
        new_svc["address_book"] = self.services[old_idx].get("address_book", {})
        new_svc["psn_book"] = self.services[old_idx].get("psn_book", {})
        self.services[old_idx] = new_svc
        self.editing_service_name = name
        
        if self.data.get("sort_services_alpha", False):
            self.services.sort(key=lambda x: x["name"].lower())
            
        self.save_services()
        self.update_service_list()
        QMessageBox.information(self, "Success", f"Service '{name}' updated successfully.")

    def delete_service(self):
        name = self.f_name.text().strip()
        if not name: return
        
        reply = QMessageBox.question(self, "Delete Service", f"Are you sure you want to delete service '{name}'?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No: return
        
        self.services = [s for s in self.services if s["name"] != name]
        self.save_services()
        self.update_service_list()
        self.reset_form_to_new()

    # --- Database Live Updates ---
    def update_active_books(self, service_names):
        if isinstance(service_names, str):
            service_names = [service_names]
            
        active_a_book = {}
        active_p_book = {}
        new_pid_map = {}
        
        for name in service_names:
            for s in self.services:
                if s["name"] == name:
                    s_a = s.get("address_book", {})
                    s_p = s.get("psn_book", {})
                    s_pid_book = s.get("pid_book", {})
                    active_a_book.update(s_a)
                    active_p_book.update(s_p)
                    
                    ow_streams = s.get("ow_streams", [])
                    if ow_streams and s.get("stream_type") == "openwebif":
                        is_multi = len(ow_streams) > 1
                        for st in ow_streams:
                            try:
                                s_pid = int(st.get("pid", 0))
                                new_pid_map[s_pid] = {
                                    "address_book": s_a, 
                                    "psn_book": s_p,
                                    "default_station": st.get("name", "") if is_multi else ""
                                }
                            except ValueError: pass
                    else:
                        raw_pid = str(s.get("pid", ""))
                        for p in raw_pid.split('/'):
                            p = p.strip()
                            if p.isdigit():
                                int_p = int(p)
                                default_st = s_pid_book.get(p, "")
                                new_pid_map[int_p] = {
                                    "address_book": s_a, 
                                    "psn_book": s_p,
                                    "default_station": default_st
                                }
                        for p, st_name in s_pid_book.items():
                            if p.isdigit():
                                int_p = int(p)
                                if int_p in new_pid_map:
                                    new_pid_map[int_p]["default_station"] = st_name
                                else:
                                    new_pid_map[int_p] = {"address_book": s_a, "psn_book": s_p, "default_station": st_name}
                    break
                
        global shared_address_book
        global shared_psn_book
        global shared_pid_map
        shared_address_book.clear()
        shared_psn_book.clear()
        shared_pid_map.clear()
        
        shared_address_book.update(active_a_book)
        shared_psn_book.update(active_p_book)
        shared_pid_map.update(new_pid_map)
        
        self.update_filter_combo()
        self.refresh_station_names()

    def update_filter_combo(self):
        current_a = self.filter_combo.currentText()
        current_p = self.filter_psn_combo.currentText()
        
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItem("ALL")
        self.filter_combo.addItem("NOT PRESENT IN DATABASE")
        
        self.filter_psn_combo.blockSignals(True)
        self.filter_psn_combo.clear()
        self.filter_psn_combo.addItem("ALL")
        self.filter_psn_combo.addItem("NOT PRESENT IN DATABASE")
        
        global shared_address_book
        global shared_psn_book
        
        station_to_addrs = {}
        for addr, name in shared_address_book.items():
            station_to_addrs.setdefault(name, []).append(addr)
            
        station_to_psns = {}
        for psn, name in shared_psn_book.items():
            station_to_psns.setdefault(name, []).append(psn)
            
        # Integration of OpenWebif bouquet stations into filtering lists
        if self.current_loaded_service:
            s = next((svc for svc in self.services if svc["name"] == self.current_loaded_service), None)
            if s and s.get("stream_type") == "openwebif":
                ow_streams = s.get("ow_streams", [])
                if len(ow_streams) > 1:
                    for st in ow_streams:
                        st_name = st.get("name", "")
                        if st_name:
                            # Add the station to both lists if it isn't already there
                            if st_name not in station_to_addrs:
                                station_to_addrs[st_name] = []
                            if st_name not in station_to_psns:
                                station_to_psns[st_name] = []
            
        if station_to_addrs:
            self.filter_combo.insertSeparator(2)
            for name in sorted(station_to_addrs.keys()):
                self.filter_combo.addItem(name, userData=station_to_addrs[name])
                
        if station_to_psns:
            self.filter_psn_combo.insertSeparator(2)
            for name in sorted(station_to_psns.keys()):
                self.filter_psn_combo.addItem(name, userData=station_to_psns[name])
        
        idx_a = self.filter_combo.findText(current_a)
        if idx_a >= 0: self.filter_combo.setCurrentIndex(idx_a)
            
        idx_p = self.filter_psn_combo.findText(current_p)
        if idx_p >= 0: self.filter_psn_combo.setCurrentIndex(idx_p)
            
        self.filter_combo.blockSignals(False)
        self.filter_psn_combo.blockSignals(False)
        self.apply_filter()

    def refresh_station_names(self):
        if hasattr(self, 'log_model'):
            for msg in self.log_model._all_rows:
                addr = msg.get("address", "")
                psn = msg.get("psn", "")
                if psn and psn in shared_psn_book:
                    msg["station"] = shared_psn_book[psn]
                elif addr in shared_address_book:
                    msg["station"] = shared_address_book[addr]
                else:
                    msg["station"] = "Unknown"
            self.apply_filter()

    def update_grid_view(self, station, address, rt_text, time_str, timestamp=None):
        st_key = station if station != "Unknown" else f"Unknown ({address})"
        
        # Retrieving the exact timestamp
        if timestamp is not None and timestamp != 0:
            try:
                dt = datetime.fromtimestamp(float(timestamp))
            except Exception:
                dt = datetime.now()
                timestamp = dt.timestamp()
        else:
            dt = datetime.now()
            timestamp = dt.timestamp()

        # Formatting with or without the date, depending on the current state of the checkbox
        display_time = dt.strftime('%d/%m/%Y %H:%M:%S') if self.chk_show_date.isChecked() else dt.strftime('%H:%M:%S')

        self.grid_table.setSortingEnabled(False)
        found = False
        for r in range(self.grid_table.rowCount()):
            if self.grid_table.item(r, 0).text() == st_key:
                item_time = self.grid_table.item(r, 1)
                item_time.setText(display_time)
                item_time.setData(Qt.UserRole, timestamp)
                self.grid_table.item(r, 2).setText(rt_text)
                found = True
                break
        if not found:
            r = self.grid_table.rowCount()
            self.grid_table.insertRow(r)
            self.grid_table.setItem(r, 0, QTableWidgetItem(st_key))
            
            item_time = QTableWidgetItem(display_time)
            item_time.setData(Qt.UserRole, timestamp)
            self.grid_table.setItem(r, 1, item_time)
            
            self.grid_table.setItem(r, 2, QTableWidgetItem(rt_text))
        self.grid_table.setSortingEnabled(True)

    # --- Connection & Streaming ---
    def remote_start(self, service_name):
        if not service_name: return
        self.bypass_change_confirmation = True
        try:
            for i in range(self.service_list.count()):
                raw_name = self.service_list.item(i).text().replace("→ ", "")
                if raw_name == service_name or self.service_list.item(i).text() == service_name:
                    self.service_list.clearSelection()
                    self.service_list.item(i).setSelected(True)
                    self.load_service_to_form(self.service_list.item(i))
                    if self.active_threads and any(t.isRunning() for t in self.active_threads):
                        self.toggle_connection() 
                    self.toggle_connection() 
                    break
        finally:
            self.bypass_change_confirmation = False

    def update_global_status(self, msg):
        active_count = sum(1 for t in self.active_threads if t.isRunning())
        if len(self.active_threads) > 1:
            self.status_label.setText(f"Status: {active_count}/{len(self.active_threads)} streams active | Last event: {msg}")
        else:
            self.status_label.setText(f"Status: {msg}")

    def on_stream_error(self, e):
        if not self.active_threads:
            return

        threads_to_stop = list(self.active_threads)
        self.active_threads.clear()
        
        # 1. Immediate closure of all network connections in parallel
        for t in threads_to_stop:
            t.running = False
            if getattr(t, 'response', None):
                try:
                    if hasattr(t.response, 'raw') and t.response.raw:
                        t.response.raw.close()
                    t.response.close()
                except Exception:
                    pass
                    
        # 2. Waiting for non-blocking release
        for t in threads_to_stop:
            if t != self.sender() and t.isRunning():
                t.wait(500)
            if getattr(t, 'aac_handle', None) and aac_lib:
                with _aac_feed_lock:
                    aac_lib.aac_decoder_close(t.aac_handle)
                t.aac_handle = None
        
        global shared_active_services
        shared_active_services = []
        
        self.btn_scroll_bottom.setVisible(False)
        self.btn_connect.setText("CONNECT TO STREAM")
        self.btn_connect.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px; outline: none;")
        self.status_label.setText("Status: Disconnected.")
        self.update_col_visibility()
        
        if self.data.get("auto_reconnect", False):
            self.status_label.setText("Status: Connection lost. Reconnection attempt in 10 seconds...")
            self.reconnect_timer.start(10000)
        else:
            self.push_to_web({"stream_error": str(e)})
            QMessageBox.critical(self, "Stream Error", str(e))

    def on_stream_finished(self):
        if self.sender() in self.active_threads:
            if not any(t.isRunning() for t in self.active_threads):
                global shared_active_services
                shared_active_services = []
                self.btn_scroll_bottom.setVisible(False)
                self.btn_connect.setText("CONNECT TO STREAM")
                self.btn_connect.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px; outline: none;")
                self.status_label.setText("Status: Stopped.")
                if self.data.get("auto_reconnect", False):
                    self.status_label.setText("Status: Stream finished. Reconnection attempt in 10 seconds...")
                    self.reconnect_timer.start(10000)
            else:
                self.update_global_status("A stream disconnected.")

    def do_reconnect(self):
        self.reconnect_timer.stop()
        if not self.active_threads and hasattr(self, 'current_loaded_service') and self.current_loaded_service:
            if not self.service_list.selectedItems():
                items = self.service_list.findItems(self.current_loaded_service, Qt.MatchExactly)
                if items:
                    self.service_list.blockSignals(True)
                    items[0].setSelected(True)
                    self.service_list.blockSignals(False)
            self.toggle_connection()

    def remote_stop(self):
        self.reconnect_timer.stop()
        if self.active_threads and any(t.isRunning() for t in self.active_threads):
            self.toggle_connection()

    def toggle_connection(self):
        self.reconnect_timer.stop()
        global shared_active_services
        if self.active_threads and any(t.isRunning() for t in self.active_threads):
            threads_to_stop = list(self.active_threads)
            self.active_threads.clear()
            
            # 1. Immediate closure of all network connections in parallel
            for t in threads_to_stop:
                t.running = False
                if getattr(t, 'response', None):
                    try:
                        if hasattr(t.response, 'raw') and t.response.raw:
                            t.response.raw.close()
                        t.response.close()
                    except Exception:
                        pass
            
            # 2. Waiting for non-blocking release
            for t in threads_to_stop:
                if t.isRunning():
                    t.wait(500)
                if getattr(t, 'aac_handle', None) and aac_lib:
                    with _aac_feed_lock:
                        aac_lib.aac_decoder_close(t.aac_handle)
                    t.aac_handle = None
            
            shared_active_services = []
            self.btn_scroll_bottom.setVisible(False)
            self.btn_connect.setText("CONNECT TO STREAM")
            self.btn_connect.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px; outline: none;")
            self.status_label.setText("Status: Disconnected.")
            self.update_col_visibility()
        else:
            # Security check: the service being created must be registered
            if hasattr(self, 'btn_save_new') and self.btn_save_new.isVisible():
                QMessageBox.warning(self, "Save Required", "The service must be saved before you can connect to it.\nPlease save it and try again.")
                return

            selected_items = self.service_list.selectedItems()
            if not selected_items:
                QMessageBox.warning(self, "Error", "Please select at least one service from the list.")
                return

            base_tp = None
            base_ow_ref = None
            pids = []
            url_pids_set = set()
            
            service_names = [item.text().replace("→ ", "") for item in selected_items]
            first_svc_name = service_names[0]
            first_stream_type = self.get_service_stream_type(first_svc_name)
            
            for svc_name in service_names:
                for s in self.services:
                    if s["name"] == svc_name:
                        tp = (s.get("freq"), s.get("pol"), s.get("sr"), s.get("msys"), s.get("mtype_en"), s.get("mtype"), s.get("fec_en"), s.get("fec"))
                        ow_ref = s.get("ow_ref", "")
                        
                        if base_tp is None and base_ow_ref is None:
                            base_tp = tp
                            base_ow_ref = ow_ref
                        elif first_stream_type == "minisatip" and base_tp != tp:
                            QMessageBox.warning(self, "Error", "Multiple services decoding requires the same transponder settings (Freq, Pol, SR, Mod, FEC).\nPlease check the selected services and try again.")
                            return
                        elif first_stream_type == "openwebif" and base_ow_ref != ow_ref:
                            QMessageBox.warning(self, "Error", "Multiple services decoding requires the exact same OpenWebif Reference.\nPlease check the selected services and try again.")
                            return
                        raw_pid = str(s.get("pid", ""))
                        for p in raw_pid.split('/'):
                            p = p.strip()
                            if p.isdigit():
                                pids.append(int(p))
                        url_pids_set.add(s.get("url_pids", "all"))
                        break
            
            if not pids and first_stream_type != "openwebif":
                QMessageBox.warning(self, "Error", "No valid PIDs found in the selected services.\nPlease check your configuration and try again.")
                return

            self.active_threads.clear()
            self.clear_output_no_confirm()
            
            self.current_loaded_service = first_svc_name
            shared_active_services = service_names
            self.update_active_books(service_names) 

            ip = self.data.get("server_ip", "")
            if not ip:
                QMessageBox.warning(self, "Error", "Receiver IP is empty.\nPlease configure it in the Settings tab before starting a stream.")
                self.btn_connect.setText("CONNECT TO STREAM")
                self.btn_connect.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px; outline: none;")
                return
            
            if first_stream_type == "openwebif":
                ow_port = self.data.get("openwebif_port", "8001")
                s = next(s for s in self.services if s["name"] == first_svc_name)
                ow_streams = s.get("ow_streams", [])
                
                if not ow_streams:
                    ow_ref = s.get("ow_ref", "")
                    if not ow_ref:
                        QMessageBox.warning(self, "Error", "No OpenWebif Reference found for the selected service.")
                        return
                    ow_streams = [{"ref": ow_ref, "uecp_source": s.get("uecp_source", "pid"), "pid": s.get("pid", "")}]
                
                for stream in ow_streams:
                    ow_ref = stream.get("ref", "")
                    if not ow_ref: continue
                    url = f"http://{ip}:{ow_port}/{ow_ref}"
                    
                    st_pids = []
                    try: st_pids.append(int(stream.get("pid", 0)))
                    except ValueError: pass
                    
                    uecp_source = stream.get("uecp_source", "pid")
                    
                    # The individual station name is passed to the thread if it is a multi-radio multiplex
                    st_name = stream.get("name", "") if len(ow_streams) > 1 else ""
                    
                    t = DecoderThread(url, st_pids, uecp_source, station_name=st_name, stream_timeout=20)
                    t.new_message.connect(self.display_message)
                    t.error_signal.connect(self.on_stream_error)
                    t.status_signal.connect(self.update_global_status)
                    t.finished.connect(self.on_stream_finished)
                    self.active_threads.append(t)
                    t.start()
            else:
                freq, pol, sr, msys, mtype_en, mtype, fec_en, fec = base_tp
                mtype_part = f"&mtype={mtype}" if mtype_en else ""
                fec_part = f"&fec={fec}" if fec_en else ""
                
                if "all" in url_pids_set:
                    final_url_pids = "all"
                else:
                    final_url_pids = ",".join(url_pids_set)
    
                port = self.data.get("server_port", "8081")
                src = 1
                for s in self.services:
                    if s["name"] == first_svc_name:
                        src = s.get("src", 1)
                        break
    
                url = f"http://{ip}:{port}/?src={src}&freq={freq}&pol={pol}&sr={sr}&msys={msys}{mtype_part}{fec_part}&pids={final_url_pids}"
                uecp_source = "pid"
                for s in self.services:
                    if s["name"] == first_svc_name:
                        uecp_source = s.get("uecp_source", "pid")
                        break
                        
                t = DecoderThread(url, pids, uecp_source, stream_timeout=10)
                t.new_message.connect(self.display_message)
                t.error_signal.connect(self.on_stream_error)
                t.status_signal.connect(self.update_global_status)
                t.finished.connect(self.on_stream_finished)
                self.active_threads.append(t)
                t.start()
            
            self.btn_connect.setText("DISCONNECT")
            self.btn_connect.setStyleSheet("background-color: #F44336; color: white; font-weight: bold; padding: 10px; outline: none;")
            self.update_col_visibility()

    # --- Display & Filter Logic ---
    def push_to_web(self, msg):
        for q in web_clients:
            q.put(msg)

    def display_message(self, msg):
        # Queues the message to avoid freezing the interface
        self.msg_queue.put(msg)

    def check_msg_filter(self, msg):
        if not hasattr(self, 'filter_combo'):
            return True
            
        addr_filter_name = self.filter_combo.currentText()
        addr_filter_addrs = self.filter_combo.currentData()
        psn_filter_name = self.filter_psn_combo.currentText()
        psn_filter_psns = self.filter_psn_combo.currentData()
        search_text = self.search_input.text().lower() if hasattr(self, 'search_input') else ""

        if addr_filter_name == "NOT PRESENT IN DATABASE":
            if msg["address"] in shared_address_book: return False
        elif addr_filter_name != "ALL":
            addr_match = (addr_filter_addrs is not None and msg["address"] in addr_filter_addrs)
            if not addr_match and msg.get("station") != addr_filter_name: return False
            
        if psn_filter_name == "NOT PRESENT IN DATABASE":
            if msg.get("psn") and msg["psn"] in shared_psn_book: return False
        elif psn_filter_name != "ALL":
            psn_match = (psn_filter_psns is not None and msg.get("psn") in psn_filter_psns)
            if not psn_match and msg.get("station") != psn_filter_name: return False
        
        if hasattr(self, 'selected_types') and msg.get("type") not in self.selected_types:
            return False

        if search_text:
            text_val = msg.get("text", "").lower()
            config_val = msg.get("config", "").lower()
            if search_text not in text_val and search_text not in config_val:
                return False

        return True

    def process_msg_queue(self):
        if self.msg_queue.empty():
            return
            
        vbar = self.log_table.verticalScrollBar()
        was_at_bottom = not self.btn_scroll_bottom.isVisible() or (vbar.value() >= vbar.maximum() - 4)
        
        batch = []
        # Micro-batch processing
        while not self.msg_queue.empty() and len(batch) < 100:
            msg = self.msg_queue.get_nowait()
            global shared_messages
            shared_messages.append(msg)
            self.push_to_web(msg)
            
            self.msg_count += 1
            
            msg_type = msg["type"]
            global shared_known_types
            if msg_type not in shared_known_types:
                shared_known_types.add(msg_type)
                if hasattr(self, 'known_types'):
                    self.known_types.add(msg_type)
                    self.selected_types.add(msg_type)
                    self.update_type_filter_button()

            if msg_type == "RT [0A]":
                self.update_grid_view(msg["station"], msg["address"], msg["text"], msg["time"], msg.get("timestamp"))
                
            batch.append(msg)
            
        self.msg_count_label.setText(f"Detections: {self.msg_count}")
        
        inserted = self.log_model.append_batch(batch, self.check_msg_filter)
        
        if inserted and was_at_bottom:
            self.log_table.scrollToBottom()

    def open_type_filter_dialog(self):
        dlg = TypeFilterDialog(self.known_types, self.selected_types, self)
        if dlg.exec_() == QDialog.Accepted:
            self.selected_types = dlg.get_selected()
            self.data["selected_types"] = list(self.selected_types)
            self.save_config()
            self.update_type_filter_button()
            self.apply_filter()

    def update_type_filter_button(self):
        if len(self.selected_types) == len(self.known_types):
            self.btn_type_filter.setText("ALL")
        elif len(self.selected_types) == 0:
            self.btn_type_filter.setText("None")
        else:
            excl = len(self.known_types) - len(self.selected_types)
            self.btn_type_filter.setText(f"{len(self.selected_types)} sel. ({excl} excl.)")

    def apply_filter(self):
        if not hasattr(self, 'log_model'):
            return
            
        search_text = self.search_input.text().lower() if hasattr(self, 'search_input') else ""
        self.highlight_delegate.set_search_text(search_text)
        self.log_model.reapply_filter(self.check_msg_filter)
        self.log_table.scrollToBottom()
        self.check_scroll_position()

    def clear_output(self):
        reply = QMessageBox.question(self, "Clear Output", "Are you sure you want to clear the output?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.clear_output_no_confirm()

    def clear_output_no_confirm(self):
        if hasattr(self, 'log_model'):
            self.log_model.clear()
        self.msg_count = 0
        self.msg_count_label.setText("Detections: 0")
        with self.msg_queue.mutex:
            self.msg_queue.queue.clear()
        global shared_messages
        shared_messages.clear()
        if hasattr(self, 'grid_table'):
            self.grid_table.setRowCount(0)
        self.push_to_web("clear")

    # --- Export / Import / Copy Functions ---
    def get_visible_table_data(self):
        headers = [self.log_model.headerData(i, Qt.Horizontal) for i in range(self.log_model.columnCount()) if not self.log_table.isColumnHidden(i)]
        rows = []
        for r_data in self.log_model._filtered_rows:
            row_cells = []
            for col_idx in range(9):
                if not self.log_table.isColumnHidden(col_idx):
                    if col_idx == 0:
                        t = r_data["time_full"] if (self.chk_show_date.isChecked() and "time_full" in r_data) else r_data["time"]
                        row_cells.append(str(t))
                    else:
                        key = {1: "crc", 2: "address", 3: "psn", 4: "station", 5: "sqc", 6: "type", 7: "config", 8: "text"}[col_idx]
                        row_cells.append(str(r_data.get(key, "")))
            rows.append(row_cells)
        return headers, rows

    def export_txt(self):
        headers, rows = self.get_visible_table_data()
        if not rows: return QMessageBox.information(self, "Export", "No data to export.")
        
        path, _ = QFileDialog.getSaveFileName(self, "Export TXT", "", "Text Files (*.txt)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    for r in rows:
                        f.write(" | ".join(r) + "\n")
                QMessageBox.information(self, "Export", "Data successfully exported to TXT.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file.\n\nError details:\n{e}")

    def export_csv(self):
        headers, rows = self.get_visible_table_data()
        if not rows: return QMessageBox.information(self, "Export", "No data to export.")
        
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if path:
            try:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    writer.writerows(rows)
                QMessageBox.information(self, "Export", "Data successfully exported to CSV.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{e}")

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Supported Files (*.txt *.csv);;CSV Files (*.csv);;Text Files (*.txt)")
        if not path: return
        
        self.log_table.setSortingEnabled(False)
        try:
            if path.endswith(".csv"):
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    next(reader, None) # Skip headers
                    for row_data in reader:
                        self.process_import_row(row_data)
            elif path.endswith(".txt"):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        row_data = line.strip().split(" | ")
                        self.process_import_row(row_data)
                            
            self.apply_filter()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file.\n\nError details:\n{e}")
        finally:
            self.log_table.setSortingEnabled(True)

    def process_import_row(self, row_data):
        if len(row_data) == 7:
            row_data.insert(3, "")
            row_data.insert(7, "")
        elif len(row_data) == 8:
            row_data.insert(3, "") 
            
        if len(row_data) == 9:
            self.insert_static_row(row_data)

    def insert_static_row(self, row_data):
        self.msg_count += 1
        self.msg_count_label.setText(f"Detections: {self.msg_count}")
        
        msg_type = normalize_type_format(row_data[6])
        row_idx = len(self.log_model._all_rows)
        
        msg_dict = {
            "time": row_data[0],
            "time_short": row_data[0].split(" ")[-1] if " " in row_data[0] else row_data[0],
            "time_full": row_data[0],
            "timestamp": row_idx,
            "crc": row_data[1],
            "address": row_data[2],
            "psn": row_data[3],
            "station": row_data[4],
            "sqc": row_data[5],
            "type": msg_type,
            "config": row_data[7],
            "text": row_data[8]
        }
        
        if msg_type == "RT [0A]":
            self.update_grid_view(row_data[4], row_data[2], row_data[8], row_data[0])
            
        global shared_messages
        shared_messages.append(msg_dict)
        self.push_to_web(msg_dict)
        
        global shared_known_types
        if msg_dict["type"] not in shared_known_types:
            shared_known_types.add(msg_dict["type"])
            if hasattr(self, 'known_types'):
                self.known_types.add(msg_dict["type"])
                self.selected_types.add(msg_dict["type"])
                self.update_type_filter_button()
                
        self.log_model.append_batch([msg_dict], self.check_msg_filter)

    def copy_all(self):
        headers, rows = self.get_visible_table_data()
        if not rows: return
        
        text = ""
        for r in rows:
            text += " | ".join(r) + "\n"
        
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Copied", "The visible data has been successfully copied to the clipboard.")

    def get_grid_table_data(self):
        headers = ["Station", "Last Update", "Last Radiotext"]
        rows = []
        for r in range(self.grid_table.rowCount()):
            st = self.grid_table.item(r, 0).text() if self.grid_table.item(r, 0) else ""
            t = self.grid_table.item(r, 1).text() if self.grid_table.item(r, 1) else ""
            rt = self.grid_table.item(r, 2).text() if self.grid_table.item(r, 2) else ""
            rows.append([st, t, rt])
        return headers, rows

    def export_grid_txt(self):
        headers, rows = self.get_grid_table_data()
        if not rows: return QMessageBox.information(self, "Export", "No data to export.")
        
        path, _ = QFileDialog.getSaveFileName(self, "Export TXT", "", "Text Files (*.txt)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    for r in rows:
                        f.write(" | ".join(r) + "\n")
                QMessageBox.information(self, "Export", "Data successfully exported to TXT.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file.\n\nError details:\n{e}")

    def export_grid_csv(self):
        headers, rows = self.get_grid_table_data()
        if not rows: return QMessageBox.information(self, "Export", "No data to export.")
        
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if path:
            try:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    writer.writerows(rows)
                QMessageBox.information(self, "Export", "Data successfully exported to CSV.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file.\n\nError details:\n{e}")

    def copy_grid_all(self):
        headers, rows = self.get_grid_table_data()
        if not rows: return
        
        text = ""
        for r in rows:
            text += " | ".join(r) + "\n"
        
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Copied", "The visible data has been successfully copied to the clipboard.")

    def show_setup_wizard(self):
        wizard = InitialSetupWizard(self)
        if wizard.exec_() == QDialog.Accepted:
            ip, mini, ow = wizard.get_data()
            self.data["server_ip"] = ip
            self.data["server_port"] = mini if mini else "8081"
            self.data["openwebif_port"] = ow if ow else "8001"
            self.srv_ip.setText(self.data["server_ip"])
            self.srv_port.setText(self.data["server_port"])
            self.ow_port.setText(self.data["openwebif_port"])
            self.save_config()

    def restart_application(self):
        self.save_config()
        import subprocess
        subprocess.Popen([sys.executable, os.path.abspath(sys.argv[0])])
        QApplication.quit()

    def closeEvent(self, event):
        self.data["window_maximized"] = self.isMaximized()
        if not self.isMaximized():
            self.data["window_width"] = self.width()
            self.data["window_height"] = self.height()
        self.save_config()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())