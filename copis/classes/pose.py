# This file is part of COPISClient.
#
# COPISClient is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# COPISClient is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with COPISClient. If not, see <https://www.gnu.org/licenses/>.

"""Provide the COPIS device Pose Class."""

from typing import List, NamedTuple

from copis.classes import Action


class Pose(NamedTuple):
    """Device pose data structure."""
    position: Action = None
    payload: List[Action] = None

    def get_actions(self) -> List[Action]:
        """Flattens the pose into its constituent list of actions and returns it."""
        actions = [self.position] if self.position else []

        if self.payload and len(self.payload) > 0:
            actions.extend(self.payload)

        return actions

    def get_seq_actions(self) -> List[Action]:
        """Works like get_actions except it still holds a spot in the list
            even if there's no position."""

        actions = [self.position] if self.position else [None]

        if self.payload and len(self.payload) > 0:
            actions.extend(self.payload)

        return actions
