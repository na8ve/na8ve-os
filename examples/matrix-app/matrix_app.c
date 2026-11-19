/*
 * Arduino Uno Q na8ve Model LED Matrix Streaming Application
 *
 * Runs inside a sandboxed WebAssembly micro-virtual machine (pVM) on na8ve-os.
 * Submits asynchronous neural inference turns to the system Model Broker
 * (pVM #1: cortex-mvp) via n8_model.h, and streams generated text responses
 * character-by-character to the onboard 12x8 LED matrix display via Core 0
 * actuator proposals (N8_OP_ACTUATE).
 */
#include "n8.h"
#include "n8_ops.h"
#include "n8_model.h"

#include <stdint.h>
#include <string.h>

/* Application Operations */
#define OP_PROMPT       0x10  /* [prompt string] -> "ok queued" */
#define OP_STATUS       0x11  /* -> "status=... text=..." */
#define OP_STREAM_STEP  0x12  /* -> "char '<c>' pos=X/Y" */
#define OP_CLEAR        0x13  /* -> "ok cleared" */
#define OP_STREAM_ALL   0x14  /* -> "ok streamed <n> chars" */
#define OP_FRAME_ASCII  0x15  /* -> Multi-line 12x8 ASCII art display */
#define OP_SCROLL_STEP  0x16  /* -> "scroll col=X/Y" marquee step */

#define MATRIX_COLS     12
#define MATRIX_ROWS     8

static uint8_t g_inbox[N8_MSG_MAX] __attribute__((aligned(4)));
static char g_text[N8_MODEL_MAX_BYTES + 1];
static int32_t g_text_len = 0;
static int32_t g_status = 1;      /* 1: idle/nothing asked; 0: text ready; negative: error */
static int32_t g_stream_idx = 0;  /* Current character position streamed */
static int32_t g_scroll_col = 0;  /* Current marquee scroll column index */
static uint8_t g_matrix[MATRIX_COLS]; /* 12 columns, 8 bits/row per column */

/* ---- 5x7 Font Bitmap (Columns 0..4, Bits 0..6 active) ---------------- */
static const uint8_t FONT_5X7[][5] = {
    /* 32: Space */   {0x00, 0x00, 0x00, 0x00, 0x00},
    /* 33: ! */       {0x00, 0x00, 0x5F, 0x00, 0x00},
    /* 34: " */       {0x00, 0x07, 0x00, 0x07, 0x00},
    /* 35: # */       {0x14, 0x7F, 0x14, 0x7F, 0x14},
    /* 36: $ */       {0x24, 0x2A, 0x7F, 0x2A, 0x12},
    /* 37: % */       {0x23, 0x13, 0x08, 0x64, 0x62},
    /* 38: & */       {0x36, 0x49, 0x55, 0x22, 0x50},
    /* 39: ' */       {0x00, 0x05, 0x03, 0x00, 0x00},
    /* 40: ( */       {0x00, 0x1C, 0x22, 0x41, 0x00},
    /* 41: ) */       {0x00, 0x41, 0x22, 0x1C, 0x00},
    /* 42: * */       {0x14, 0x08, 0x3E, 0x08, 0x14},
    /* 43: + */       {0x08, 0x08, 0x3E, 0x08, 0x08},
    /* 44: , */       {0x00, 0x50, 0x30, 0x00, 0x00},
    /* 45: - */       {0x08, 0x08, 0x08, 0x08, 0x08},
    /* 46: . */       {0x00, 0x60, 0x60, 0x00, 0x00},
    /* 47: / */       {0x20, 0x10, 0x08, 0x04, 0x02},
    /* 48: 0 */       {0x3E, 0x51, 0x49, 0x45, 0x3E},
    /* 49: 1 */       {0x00, 0x42, 0x7F, 0x40, 0x00},
    /* 50: 2 */       {0x42, 0x61, 0x51, 0x49, 0x46},
    /* 51: 3 */       {0x21, 0x41, 0x45, 0x4B, 0x31},
    /* 52: 4 */       {0x18, 0x14, 0x12, 0x7F, 0x10},
    /* 53: 5 */       {0x27, 0x45, 0x45, 0x45, 0x39},
    /* 54: 6 */       {0x3C, 0x4A, 0x49, 0x49, 0x30},
    /* 55: 7 */       {0x01, 0x71, 0x09, 0x05, 0x03},
    /* 56: 8 */       {0x36, 0x49, 0x49, 0x49, 0x36},
    /* 57: 9 */       {0x06, 0x49, 0x49, 0x29, 0x1E},
    /* 58: : */       {0x00, 0x36, 0x36, 0x00, 0x00},
    /* 59: ; */       {0x00, 0x56, 0x36, 0x00, 0x00},
    /* 60: < */       {0x08, 0x14, 0x22, 0x41, 0x00},
    /* 61: = */       {0x14, 0x14, 0x14, 0x14, 0x14},
    /* 62: > */       {0x00, 0x41, 0x22, 0x14, 0x08},
    /* 63: ? */       {0x02, 0x01, 0x51, 0x09, 0x06},
    /* 64: @ */       {0x32, 0x49, 0x79, 0x41, 0x3E},
    /* 65: A */       {0x7E, 0x11, 0x11, 0x11, 0x7E},
    /* 66: B */       {0x7F, 0x49, 0x49, 0x49, 0x36},
    /* 67: C */       {0x3E, 0x41, 0x41, 0x41, 0x22},
    /* 68: D */       {0x7F, 0x41, 0x41, 0x22, 0x1C},
    /* 69: E */       {0x7F, 0x49, 0x49, 0x49, 0x41},
    /* 70: F */       {0x7F, 0x09, 0x09, 0x09, 0x01},
    /* 71: G */       {0x3E, 0x41, 0x49, 0x49, 0x7A},
    /* 72: H */       {0x7F, 0x08, 0x08, 0x08, 0x7F},
    /* 73: I */       {0x00, 0x41, 0x7F, 0x41, 0x00},
    /* 74: J */       {0x20, 0x40, 0x41, 0x3F, 0x01},
    /* 75: K */       {0x7F, 0x08, 0x14, 0x22, 0x41},
    /* 76: L */       {0x7F, 0x40, 0x40, 0x40, 0x40},
    /* 77: M */       {0x7F, 0x02, 0x0C, 0x02, 0x7F},
    /* 78: N */       {0x7F, 0x04, 0x08, 0x10, 0x7F},
    /* 79: O */       {0x3E, 0x41, 0x41, 0x41, 0x3E},
    /* 80: P */       {0x7F, 0x09, 0x09, 0x09, 0x06},
    /* 81: Q */       {0x3E, 0x41, 0x51, 0x21, 0x5E},
    /* 82: R */       {0x7F, 0x09, 0x19, 0x29, 0x46},
    /* 83: S */       {0x46, 0x49, 0x49, 0x49, 0x31},
    /* 84: T */       {0x01, 0x01, 0x7F, 0x01, 0x01},
    /* 85: U */       {0x3F, 0x40, 0x40, 0x40, 0x3F},
    /* 86: V */       {0x1F, 0x20, 0x40, 0x20, 0x1F},
    /* 87: W */       {0x3F, 0x40, 0x38, 0x40, 0x3F},
    /* 88: X */       {0x63, 0x14, 0x08, 0x14, 0x63},
    /* 89: Y */       {0x07, 0x08, 0x70, 0x08, 0x07},
    /* 90: Z */       {0x61, 0x51, 0x49, 0x45, 0x43}
};

static const uint8_t GLYPH_UNKNOWN[5] = {0x7F, 0x41, 0x41, 0x41, 0x7F}; /* Box border */

static const uint8_t *font_get_glyph(char c)
{
    /* Map lowercase ASCII to uppercase for high-contrast 5x7 rendering */
    if (c >= 'a' && c <= 'z') c = (char)(c - 32);
    if (c >= 32 && c <= 90) {
        return FONT_5X7[c - 32];
    }
    return GLYPH_UNKNOWN;
}

/* ---- 12x8 LED Matrix Framebuffer Management -------------------------- */

static void matrix_clear(void)
{
    for (int i = 0; i < MATRIX_COLS; i++) {
        g_matrix[i] = 0;
    }
}

static void matrix_render_char(char c)
{
    matrix_clear();
    const uint8_t *glyph = font_get_glyph(c);
    /* Center 5 font columns horizontally across 12 physical columns (cols 3..7) */
    for (int i = 0; i < 5; i++) {
        g_matrix[3 + i] = glyph[i];
    }
}

static void dispatch_matrix_actuation(char c)
{
    /* Propose actuation to Core 0 Actuator Safety Monitor */
    char cmd[96];
    int at = 0;
    n8_put(cmd, &at, sizeof(cmd), "act target=matrix.glyph state=ok char=");
    char c_str[2] = { c ? c : ' ', '\0' };
    n8_put(cmd, &at, sizeof(cmd), c_str);
    n8_put(cmd, &at, sizeof(cmd), " cols=");
    n8_put_hex(cmd, &at, sizeof(cmd), g_matrix, MATRIX_COLS);

    n8_ipc_send(0, N8_OP_ACTUATE, cmd, at);

    /* Also emit telemetry to the kernel console ring */
    char log_buf[64];
    int log_at = 0;
    n8_put(log_buf, &log_at, sizeof(log_buf), "matrix: char='");
    n8_put(log_buf, &log_at, sizeof(log_buf), c_str);
    n8_put(log_buf, &log_at, sizeof(log_buf), "' streamed to Uno Q 12x8 LED\n");
    n8_log(log_buf, log_at);
}

/* ---- Application Lifecycle Exports ----------------------------------- */

N8_EXPORT(n8_init) int32_t n8_init(void)
{
    matrix_clear();
    n8_log("matrix: Uno Q LED matrix streamer active\n", 40);
    return 0;
}

N8_EXPORT(n8_inbox) int32_t n8_inbox(void)
{
    return (int32_t)(uintptr_t)g_inbox;
}

static void handle_prompt(int32_t len)
{
    if (n8_model_pending()) {
        return (void)n8_reply_str("ERR busy");
    }
    const int32_t rc = n8_model_request((const char *)g_inbox, len, 32);
    if (rc == N8_MODEL_E_BUSY) return (void)n8_reply_str("ERR busy");
    if (rc == N8_MODEL_E_SIZE) return (void)n8_reply_str("ERR size");
    if (rc != 0) return (void)n8_reply_str("ERR gate");

    g_status = 1;
    g_text[0] = '\0';
    g_text_len = 0;
    g_stream_idx = 0;
    g_scroll_col = 0;
    matrix_clear();
    n8_reply_str("ok queued");
}

static void handle_status(void)
{
    char r[128];
    int at = 0;
    if (n8_model_pending()) {
        return (void)n8_reply_str("pending");
    }
    if (g_status == 1) {
        return (void)n8_reply_str("nothing asked");
    }
    if (g_status < 0) {
        n8_put(r, &at, sizeof(r), "ERR ");
        if (g_status == N8_MODEL_E_RATE) n8_put(r, &at, sizeof(r), "rate");
        else if (g_status == N8_MODEL_E_MODEL) n8_put(r, &at, sizeof(r), "no-model");
        else n8_put(r, &at, sizeof(r), "broker");
        return (void)n8_reply_str(r);
    }
    n8_put(r, &at, sizeof(r), "text ");
    n8_put(r, &at, sizeof(r), g_text);
    n8_put(r, &at, sizeof(r), " | stream ");
    n8_put_u(r, &at, sizeof(r), (uint64_t)g_stream_idx);
    n8_put(r, &at, sizeof(r), "/");
    n8_put_u(r, &at, sizeof(r), (uint64_t)g_text_len);
    n8_reply_str(r);
}

static void handle_stream_step(void)
{
    if (g_status == 1) return (void)n8_reply_str("nothing asked");
    if (g_status < 0) return (void)n8_reply_str("ERR model");
    if (g_stream_idx >= g_text_len) return (void)n8_reply_str("stream done");

    char c = g_text[g_stream_idx++];
    matrix_render_char(c);
    dispatch_matrix_actuation(c);

    char r[64];
    int at = 0;
    n8_put(r, &at, sizeof(r), "char '");
    char c_str[2] = { c, '\0' };
    n8_put(r, &at, sizeof(r), c_str);
    n8_put(r, &at, sizeof(r), "' pos=");
    n8_put_u(r, &at, sizeof(r), (uint64_t)g_stream_idx);
    n8_put(r, &at, sizeof(r), "/");
    n8_put_u(r, &at, sizeof(r), (uint64_t)g_text_len);
    n8_reply_str(r);
}

static void handle_stream_all(void)
{
    if (g_status == 1) return (void)n8_reply_str("nothing asked");
    if (g_status < 0) return (void)n8_reply_str("ERR model");
    
    /* Dispatch continuous looping multi-character scroll proposal to Core 0 */
    char cmd[128];
    int at = 0;
    n8_put(cmd, &at, sizeof(cmd), "act target=matrix.glyph state=ok mode=scroll loop=1 text=");
    n8_put(cmd, &at, sizeof(cmd), g_text);
    n8_ipc_send(0, N8_OP_ACTUATE, cmd, at);

    int count = g_text_len - g_stream_idx;
    if (count < 0) count = 0;
    g_stream_idx = g_text_len;

    char r[64];
    int r_at = 0;
    n8_put(r, &r_at, sizeof(r), "ok streamed ");
    n8_put_u(r, &r_at, sizeof(r), (uint64_t)count);
    n8_put(r, &r_at, sizeof(r), " chars (looping)");
    n8_reply_str(r);
}

static void handle_clear(void)
{
    matrix_clear();
    g_stream_idx = 0;
    g_scroll_col = 0;

    /* Propose clear actuation */
    const char clear_cmd[] = "act target=matrix.glyph state=clear";
    n8_ipc_send(0, N8_OP_ACTUATE, clear_cmd, (int32_t)strlen(clear_cmd));
    n8_log("matrix: 12x8 LED cleared\n", 25);
    n8_reply_str("ok cleared");
}

static void handle_scroll_step(void)
{
    if (g_status == 1) return (void)n8_reply_str("nothing asked");
    if (g_status < 0) return (void)n8_reply_str("ERR model");
    const int32_t total_cols = g_text_len * 6 + MATRIX_COLS;
    if (total_cols <= 0) return (void)n8_reply_str("nothing asked");
    if (g_scroll_col >= total_cols) {
        g_scroll_col = 0; /* Loop back to beginning for continuous multi-character stroll */
    }

    /* Determine next column byte to enter from right */
    uint8_t next_col = 0;
    int32_t char_idx = g_scroll_col / 6;
    int32_t col_in_char = g_scroll_col % 6;
    if (char_idx < g_text_len) {
        if (col_in_char < 5) {
            next_col = font_get_glyph(g_text[char_idx])[col_in_char];
        } else {
            next_col = 0; /* 1-column spacing between characters */
        }
    }

    /* Shift framebuffer left by 1 column */
    for (int i = 0; i < MATRIX_COLS - 1; i++) {
        g_matrix[i] = g_matrix[i + 1];
    }
    g_matrix[MATRIX_COLS - 1] = next_col;
    g_scroll_col++;

    /* Dispatch actuation frame */
    char cur_c = char_idx < g_text_len ? g_text[char_idx] : ' ';
    dispatch_matrix_actuation(cur_c);

    char r[64];
    int at = 0;
    n8_put(r, &at, sizeof(r), "scroll col=");
    n8_put_u(r, &at, sizeof(r), (uint64_t)g_scroll_col);
    n8_put(r, &at, sizeof(r), "/");
    n8_put_u(r, &at, sizeof(r), (uint64_t)total_cols);
    n8_reply_str(r);
}

static void handle_frame_ascii(void)
{
    char r[256];
    int at = 0;
    n8_put(r, &at, sizeof(r), "+------------+\n");
    for (int row = 0; row < MATRIX_ROWS; row++) {
        n8_put(r, &at, sizeof(r), "|");
        for (int col = 0; col < MATRIX_COLS; col++) {
            int on = (g_matrix[col] >> row) & 1;
            n8_put(r, &at, sizeof(r), on ? "*" : ".");
        }
        n8_put(r, &at, sizeof(r), "|\n");
    }
    n8_put(r, &at, sizeof(r), "+------------+");
    n8_reply_str(r);
}

N8_EXPORT(n8_on_message) int32_t n8_on_message(int32_t from, int32_t op, int32_t len)
{
    if (len < 0 || len > N8_MSG_MAX) return n8_reply_str("ERR len"), 0;

    /* 1. Asynchronous response from Model Broker (pVM #1) */
    if (op == N8_MODEL_REPLY && from == N8_MODEL_BROKER) {
        const int32_t n = n8_model_parse(g_inbox, len, g_text, sizeof(g_text));
        if (n < 0) {
            g_status = n;
            return 0;
        }
        g_text_len = n;
        g_status = 0;
        g_stream_idx = 0;
        g_scroll_col = 0;

        /* Immediately stream first character to the 12x8 matrix */
        if (g_text_len > 0) {
            char first = g_text[g_stream_idx++];
            matrix_render_char(first);
            dispatch_matrix_actuation(first);
        }
        return 0; /* Inbound replies require no reply */
    }

    /* 2. Application Dispatch Loop */
    switch (op) {
    case N8_OP_PING:     n8_reply_str("pong matrix"); break;
    case OP_PROMPT:      handle_prompt(len); break;
    case OP_STATUS:      handle_status(); break;
    case OP_STREAM_STEP: handle_stream_step(); break;
    case OP_CLEAR:       handle_clear(); break;
    case OP_STREAM_ALL:  handle_stream_all(); break;
    case OP_FRAME_ASCII: handle_frame_ascii(); break;
    case OP_SCROLL_STEP: handle_scroll_step(); break;
    default:             n8_reply_str("ERR op");
    }
    return 0;
}

#if N8_TEST_BUILD
uint8_t *matrix_inbox(void) { return g_inbox; }
const uint8_t *matrix_framebuffer(void) { return g_matrix; }
#endif

