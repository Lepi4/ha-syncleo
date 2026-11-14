> Maintained fork of [DeKaN/ha-syncleo](https://github.com/DeKaN/ha-syncleo).
> This fork includes a handshake recovery fix on top of 0.7.0. A missing full
> handshake reply now times out after 10 seconds, allowing automatic reconnect.
> See [local patch details and offline tests](custom_components/syncleo/LOCAL-PATCH.md).

# Syncleo (Rusclimate/Polaris) WiFi (UDP) Integration for Home Assistant
[![GitHub Release][releases-shield]][releases]
[![Downloads][download-latest-shield]][releases]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]
[![Lint](https://github.com/Lepi4/ha-syncleo/actions/workflows/lint.yml/badge.svg)](https://github.com/Lepi4/ha-syncleo/actions/workflows/lint.yml)
[![Validate](https://github.com/Lepi4/ha-syncleo/actions/workflows/validate.yaml/badge.svg)](https://github.com/Lepi4/ha-syncleo/actions/workflows/validate.yaml)

Integration to control devices using Syncleo IoT (Rusclimate/Polaris) UDP protocol.  
Integration **doesn't** use MQTT, but your device should be visible in mDNS.

**Requirements:** Home Assistant 2026.10.0 or newer, local UDP connectivity and
mDNS discovery. [Русская инструкция](README_RU.md) · [Changelog](CHANGELOG.md) ·
[Report a fork issue](https://github.com/Lepi4/ha-syncleo/issues).

This fork retains the upstream MIT license. See [LICENSE](LICENSE) and the
[pysyncleo notice](custom_components/syncleo/PYSYNCLEO-LICENSE.txt).

## FAQ
Q: How to get "Share URL"?  
A: Open device settings in mobile app, go to "Access control" screen and press "Share" button. You can see QR code on new screen, press "Share" button to get "Share URL" as text.

Q: How to find device type for my device?  
A: Look at your "Share URL", it has a specific format: `rusklimat://device-share/rusclimate/<DEVICE_TYPE>/<MAC_ADDRESS>>?token=<TOKEN>&name=<DEVICE_NAME>&deviceLocation=<LOCATION_NAME>&<DEVICE_ATTRIBUTES>`.


## [Supported models][models]

## Installation

<!-- ha-marketplace:exclude-start -->
### Install from Marketplace / HACS

In Home Assistant 2026.11+, open **Settings → Marketplace → Add from link** and add
`https://github.com/Lepi4/ha-syncleo`. Install the latest published release.
Its `syncleo.zip` asset contains the integration files, ready for Marketplace.

For HACS, add the same URL as a custom repository with category **Integration**.
[![Open your Home Assistant instance and open this repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Lepi4&repository=ha-syncleo&category=Integration)

The upstream repository and this fork share the `syncleo` domain. Use only one
source for updates. Back up Home Assistant before switching an existing installation;
do not delete devices or integration configuration just to retry a failed download.
After an update, restart Home Assistant when prompted.

If installation previously tried `releases/download/main/syncleo.zip`, refresh
the repository information and select a published release instead of `main`.

### Manual installation

Download `syncleo.zip` from [Releases][releases], extract its contents into
`<config>/custom_components/syncleo/`, then restart Home Assistant. Do not place
the repository's source ZIP or an extra `syncleo/` folder inside that directory.
<!-- ha-marketplace:exclude-end -->

### Device setup

Then add device via these steps:
1. Wait for autodiscovery (it's important).
1. Paste "Share URL" from mobile app at adding device.
1. Fix Vendor/Model if needed.

## Virtual Temperature Sensor
By default, heaters use their internal sensor to measure room temperature and control heating level. Because sensor is near the heater, this internal reading can be inaccurate. Also, heaters support combining into a group, where one of them is broacasting temperature from its sensor to others.
The Virtual Temperature sensor solves this by allowing you to link any Home Assistant temperature sensor (e.g., a Zigbee room thermometer) directly to the heater over the local network using mDNS as real device does.

How to set it up:
1. Create the Virtual Sensor:
    1. Go to Settings > Devices & Services > Add Integration and search for Syncleo.
    1. Choose the existing Home Assistant temperature entity you want to use as the source for Virtual Sensor. This creates a virtual mDNS broadcaster on your network. Attention: this is a virtual device with minimum of implementation, don't add it in a mobile app!
1. Link the sensor to heater:
    1. Go to your Syncleo Heater's device page in Home Assistant.
    1. Locate the "Temperature Source" dropdown menu.
    1. Change it from the internal sensor to the newly created Virtual Sensor.

<!---->
[hacs]: https://github.com/hacs/integration
[releases-shield]: https://img.shields.io/github/v/release/Lepi4/ha-syncleo?style=for-the-badge
[releases]: https://github.com/Lepi4/ha-syncleo/releases
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/Lepi4/ha-syncleo.svg?style=for-the-badge
[download-latest-shield]: https://img.shields.io/github/downloads/Lepi4/ha-syncleo/latest/total?style=for-the-badge
[models]: supported_models.md
