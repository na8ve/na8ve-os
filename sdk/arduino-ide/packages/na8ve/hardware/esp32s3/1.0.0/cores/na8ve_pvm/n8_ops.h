/* Message opcodes and limits shared by na8ve Arduino applications.
 * A reply copies the call opcode with bit 31 (0x80000000u) set. */
#ifndef N8_OPS_H
#define N8_OPS_H

#define N8_MSG_MAX 1024

#define N8_OP_PING 1       /* -> "pong <name>" */
#define N8_OP_MODEL_TURN 4 /* [max u8] prompt -> "turn out=<hex> us=" */

#endif

