# SatRDS-Monitor
SatRDS Monitor is a real-time Python-based monitor and decoder for RDS/UECP data from satellite radio services. By connecting directly to a satellite receiver, it captures RDS data transmitted via satellite, which can then be used to feed FM or DAB+ transmitters.
<br>
<br>
It is natively compatible with Windows (and was tested on Windows 11), but also logically with Linux (although not tested ; AAC streams decoding is not supported on this OS).
<br>
<br>
Data can be retrieved via Minisatip and OpenWebif streams (the latter being necessary for Enigma2 receivers when handling specific streams incompatible with Minisatip).
<br>
<br>
RDS/UECP information can be collected either through dedicated data channels (PIDs) or via MP2 and AAC audio streams.
<br>
<br>
The software interface allows users to create a database of addresses, PSNs, and PIDs, making it easy to identify stations and determine exactly which station a specific data packet belongs to.
<br>
<br>
An authentication-protected web interface is also included, allowing remote control of the software and real-time decoding monitoring.
<br>
<br>
<img width="900" alt="satrdsmonitor-1" src="https://github.com/user-attachments/assets/0a1a8659-e489-4d91-8dd3-81bd84f5c244" />
<img width="900" alt="satrdsmonitor-2" src="https://github.com/user-attachments/assets/7a3f9078-37ba-4d08-a276-25bdc78f4422" />
## Contribution credits
SatRDS Monitor is based on [@mrwish7](https://github.com/mrwish7/)'s project, DVB-UECP-Tools. [Click here to find more about it.](https://github.com/mrwish7/DVB-UECP-Tools)
<br>
A huge thank you to him for his help and his work, without which creating this software would not have been possible!
## Requirements
### To use SatRDS Monitor, you need:
• Python 3.8+
<br>
• A satellite receiver connected to your network, equipped with Minisatip or OpenWebif (for Enigma2 receivers).
<br>
<br>
<b>(Note for Python on Windows: Make sure to check the "Add Python to PATH" box during the installation process)</b>
## Installation
### • For Windows
1 - Install the latest Python version [by clicking here.](https://www.python.org/downloads/)
<br>
<b>Make sure to check the "Add Python to PATH" box during the installation process.</b>
<br>
<br>
2 - Using the terminal (cmd) or Powershell, go to the path of your choice and clone the repository:
<br>
`git clone https://github.com/LucasGallone/SatRDS-Monitor.git`
<br>
`cd SatRDS-Monitor`
<br>
Otherwise, simply download the ZIP [by clicking here](https://github.com/LucasGallone/SatRDS-Monitor/archive/refs/heads/main.zip), and extract the content in a folder.
<br>
<br>
3 - Install the required Python dependencies using pip:
<br>
`pip install PyQt5 requests Flask`
<br>
<br>
4 - Launch the software:
<br>
`python SatRDSMonitor.py`
### • For Linux
<b>IMPORTANT NOTE: As the AAC library used by the software is not compatible with Linux, it is not possible to decode AAC streams with the software. Only dedicated PID data and MP2 streams can be decoded.</b>
<br>
<br>
1 - Open a terminal and install Python, the pip package manager, and the libraries required for PyQt5:
<br>
`sudo apt update`
<br>
`sudo apt install -y python3 python3-pip python3-pyqt5 git`
<br>
<br>
2 - Go to the path of your choice and clone the repository:
<br>
`git clone https://github.com/LucasGallone/SatRDSMonitor.git`
<br>
`cd SatRDS-Monitor`
<br>
<br>
3 - Install the Python dependencies if you don't have them yet:
<br>
`pip3 install requests Flask`
<br>
<br>
4 - Launch the software:
<br>
`python3 SatRDSMonitor.py`
## Contribute to add services to the database
The software includes a database containing Minisatip (transponder) and/or OpenWebif information for services available on various satellites.
<br>
This database is initialized upon the first startup.
<br>
<br>
These presets allow you to connect directly to a service without needing to perform your own searches or manual configuration.
<br>
A database of identified stations for each service is also included.
<br>
<br>
You can always create your own services if required.
- - -
Do you know of a service that isn't in this database?
<br>
<br>
Please feel free to report it in the "Issues" section, providing as much information as possible (transponder data for Minisatip streams or reference(s) for OpenWebif streams, the satellite hosting the service, PIDs, addresses, and PSN).
