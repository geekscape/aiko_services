#!/usr/bin/env python3
#
# Usage
# ~~~~~
# python -i -c "import z"
# >>> z.xgo.read_battery()
# >>> z.xgo.arm(80, -80)
# >>> z.xgo.pitch(10)  # Pitch face down (don't want arm to hit the floor)
#
# >>> z.xgo.claw(0)
# >>> z.zgo.attitude("p", 15)  # Pitch face down (maximum)
# >>> z.xgo.arm(130, -40)
# >>> z.xgo.claw(255)
# >>> z.zgo.attitude("p", 0)
# >>> z.xgo.arm(130, 0)   # Claw and contents in the middle of camera view
# >>> z.xgo.arm(130, 50)  # Claw and contents out of camera view
#
# >>> z.xgo.translation("z", 75)
# >>> z.xgo.arm(90, 0)
# >>> z.xgo.attitude("p", 15)
# >>> z.xgo.arm(90, -30)
# >>> z.xgo.claw(255)

from xgolib import XGO
xgo = XGO(port='/dev/ttyAMA0',version="xgomini")

xgo.reset()
xgo.claw(0)
# xgo.arm(80, -80)

print(f"Battery: {xgo.read_battery()}%")
