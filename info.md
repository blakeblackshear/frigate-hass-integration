[![GitHub Release][releases-shield]][releases]
[![License][license-shield]][license]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]

_Component to integrate with [frigate][frigate]._

**This component will set up the following platforms.**

Platform | Description
-- | --
`media_browser` | Rich media browser for Frigate recordings.
`sensor` | Sensors for monitoring frigate performance.
`camera` | Frigate camera entities.

![example][exampleimg]

{% if not installed %}
## Installation

1. Click install.
1. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Frigate".

{% endif %}


## Configuration is done in the UI

<!---->

***

[frigate]: https://github.com/blakeblackshear/frigate
[commits]: https://github.com/blakeblackshear/frigate/commits/master
[hacs]: https://hacs.xyz
[exampleimg]: frigate.png
[license]: https://github.com/blakeblackshear/frigate/blob/main/LICENSE
[releases]: https://github.com/blakeblackshear/frigate/releases
[user_profile]: https://github.com/blakeblackshear
