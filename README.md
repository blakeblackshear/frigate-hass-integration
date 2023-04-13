<!-- markdownlint-disable first-line-heading -->
<!-- markdownlint-disable no-inline-html -->

<img src="https://raw.githubusercontent.com/blakeblackshear/frigate-hass-integration/master/images/frigate.png"
     alt="Frigate icon"
     width="35%"
     align="right"
     style="float: right; margin: 10px 0px 20px 20px;" />

[![GitHub Release](https://img.shields.io/github/release/blakeblackshear/frigate-hass-integration.svg?style=flat-square)](https://github.com/blakeblackshear/frigate-hass-integration/releases)
[![Build Status](https://img.shields.io/github/actions/workflow/status/blakeblackshear/frigate-hass-integration/build.yaml?branch=master&style=flat-square)](https://github.com/blakeblackshear/frigate-hass-integration/actions/workflows/build.yaml)
[![Test Coverage](https://img.shields.io/codecov/c/gh/blakeblackshear/frigate-hass-integration?style=flat-square)](https://app.codecov.io/gh/blakeblackshear/frigate-hass-integration/)
[![License](https://img.shields.io/github/license/blakeblackshear/frigate-hass-integration.svg?style=flat-square)](LICENSE)
[![hacs](https://img.shields.io/badge/HACS-default-orange.svg?style=flat-square)](https://hacs.xyz)

# Frigate Home Assistant Integration

Provides the following:

- Rich media browser with thumbnails and navigation
- Sensor entities (Camera FPS, Detection FPS, Process FPS, Skipped FPS, Objects detected)
- Binary Sensor entities (Object motion)
- Camera entities (Live view, Object detected snapshot)
- Switch entities (Clips, Detection, Snapshots, Improve Contrast)
- Support for multiple Frigate instances.

## Installation

Easiest install is via [HACS](https://hacs.xyz/):

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=blakeblackshear&repository=frigate-hass-integration&category=integration)

`HACS -> Integrations -> Explore & Add Repositories -> Frigate`

Notes:

- HACS does not "configure" the integration for you. You must go to `Configuration > Integrations` and add Frigate after installing via HACS.
- The `mqtt` integration must be installed and configured in order for the Frigate integration to work. As manual configuration is required for the `mqtt` setup, this cannot happen automatically.

For manual installation for advanced users, copy `custom_components/frigate` to
your `custom_components` folder in Home Assistant.

Please visit the [main Frigate
documentation](https://docs.frigate.video/integrations/home-assistant/)
for full installation instructions of this integration.

### Media Browsing

You will also need [media_source](https://www.home-assistant.io/integrations/media_source/) enabled in your Home Assistant configuration for the Media Browser to appear.

### Lovelace Card

There is also a [companion Lovelace card](https://github.com/dermotduffy/frigate-hass-card) for use with this integration.

<img src="https://raw.githubusercontent.com/blakeblackshear/frigate-hass-integration/master/images/lovelace-card.png">

## Documentation

For full usage instructions, please see the [central Frigate documentation](https://docs.frigate.video/integrations/home-assistant/).
