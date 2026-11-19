/* Default actuator input stub in a sandboxed pVM: always returns unknown (-1).
 * Physical hardware interlocks are evaluated exclusively by Core 0's compiled policy table;
 * userland pVMs have no direct pin access. */
#include "cx_act.h"

int cx_act_input(int pin)
{
    (void)pin;
    return -1;
}
