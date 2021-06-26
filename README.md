[![GitHub Release](https://img.shields.io/github/release/blakeblackshear/frigate-hass-integration.svg?style=flat-square)](https://github.com/blakeblackshear/frigate-hass-integration/releases)
[![Build Status](https://img.shields.io/github/workflow/status/blakeblackshear/frigate-hass-integration/Build?style=flat-square)](https://github.com/blakeblackshear/frigate-hass-integration/actions/workflows/build.yaml)
[![Test Coverage](https://img.shields.io/codecov/c/gh/blakeblackshear/frigate-hass-integration?style=flat-square)](https://app.codecov.io/gh/blakeblackshear/frigate-hass-integration/)
[![License](https://img.shields.io/github/license/blakeblackshear/frigate-hass-integration.svg?style=flat-square)](LICENSE)
[![hacs](https://img.shields.io/badge/HACS-default-orange.svg?style=flat-square)](https://hacs.xyz)

# Frigate Home Assistant Integration

Provides the following:
- Rich media browser with thumbnails and navigation
- Sensor entities (Camera FPS, Detection FPS, Process FPS, Skipped FPS, Objects detected)
- Binary Sensor entities (Object motion)
- Camera entities (Live view, Object detected snapshot)
- Switch entities (Clips, Detection, Snapshots)
- Support for multiple Frigate instances.

## Installation

Copy `custom_components/frigate` to your `custom_components` folder in Home Assistant. Also available via HACS as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories). Note that HACS does not "configure" the integration for you. You must go to `Configuration > Integrations` and add Frigate after installing via HACS.

You will also need [media_source](https://www.home-assistant.io/integrations/media_source/) enabled in your Home Assistant configuration for the Media Browser to appear.

## Documentation

For full usage instructions, please see the [central Frigate documentation](https://blakeblackshear.github.io/frigate/usage/home-assistant/).