/* The messages a pVM handles, shared by user apps and the kernel's console.
 * A reply's op copies the call opcode with reply bit (0x80000000u) set; its bytes are text unless noted. */
#ifndef N8_OPS_H
#define N8_OPS_H

#define N8_MSG_MAX 1024

#define N8_OP_PING 1          /* -> "pong <name>" */
#define N8_OP_MODEL_OPEN 2    /* [bits u8: 32, 8 or 4] -> "model name= width= bytes= at= ..." (cortex-mvp) */
#define N8_OP_MODEL_RECEIPT 3 /* bytes -> "receipt n= logits= synapse= sat= us=": n8vm_run's digests */
#define N8_OP_MODEL_TURN 4    /* [max u8] prompt -> "turn out=<hex> us=": greedy, the model.turn of 06 */
#define N8_OP_STORE_QUERY 5   /* text -> the store's rows (needs a store grant) */
#define N8_OP_CHAT 6          /* -> "ok" or "ERR chat ...": a chat turn, its request read through chat_in,
                               * its lines streamed through emit */
#define N8_OP_CHAT_NEW 7      /* -> "ok": a new conversation, the account emptied */
#define N8_OP_CHAT_PROFILE 8  /* -> "profile x50 ...": the turn's per-byte pieces timed (a diagnostic) */
#define N8_OP_TABLE 9         /* -> "table n=... name{states} ...": the actuator table compiled into the app */
#define N8_OP_ACTUATE 10      /* sent to pVM 0, needs an act grant: a proposal the board's actuator
                               * policy table decides. "act target=<actuator> state=<state>" names the
                               * table's own actuator and state (fan high, light on, mister on), the same
                               * on every board; "act pin=<n> state=<0|1>" names a pin of this board,
                               * state 0 its safe state. Text after the two fields is a note for the log */
#define N8_OP_PROBE_READ 0x50  /* [addr u32 LE] -> "read value=": a load at addr of its own memory */
#define N8_OP_PROBE_IPC 0x51   /* [to u8] -> "ipc rc=": a send to pVM `to` */
#define N8_OP_PROBE_STORE 0x52 /* -> "store rc=": a store query */
#define N8_OP_PROBE_SPIN 0x53  /* never returns: its budget must stop it */
#define N8_OP_PROBE_FLASH 0x54 /* [off u32 LE] -> "flash rc=": 16 bytes of "model" */

#endif
