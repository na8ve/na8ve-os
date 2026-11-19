/*
 * na8ve-os Image & Visual Perception Edge Application
 *
 * Runs inside a sandboxed WebAssembly micro-virtual machine (pVM) on na8ve-os.
 * Implements real-time camera sensing, foveated saccade classification,
 * zero-raw-image-persistence privacy gating, Core 0 actuator safety proposals,
 * and cognitive visual turns via Model Broker (pVM #1: cortex-mvp).
 */
#include "n8.h"
#include "n8_ops.h"
#include "n8_model.h"

#include <stdint.h>
#include <string.h>

/* Application Operations */
#define OP_PROBE          0x02  /* -> "cam sensor=... pid=... view=72 status=ready" */
#define OP_CAPTURE        0x10  /* -> "ok captured scene=<name> (volatile DMA cleared)" */
#define OP_CLASSIFY       0x11  /* -> "class=<name> p=<prob> ms=<lat> saccades=8" */
#define OP_STATUS         0x12  /* -> "class=<name> p=<prob> bbox=[...] privacy=zero_raw_persisted" */
#define OP_ASCII_VIEW     0x13  /* -> Multi-line camera ASCII art viewport */
#define OP_COGNITIVE_TURN 0x14  /* -> "ok queued" (dispatches situational turn to cortex-mvp) */
#define OP_ACTUATE        0x15  /* -> "ok proposed act target=<target> state=<state>" */
#define OP_SCENE          0x16  /* [scene_id: 0..4] -> "ok scene=<name>" */

#define VIEWPORT_WIDTH   32
#define VIEWPORT_HEIGHT  8

/* Pre-calibrated Benchmark Scenes */
typedef struct {
    const char *name;
    const char *label;
    uint32_t confidence_pct; /* 0..100 */
    uint16_t bbox[4];        /* x1, y1, x2, y2 */
    const char *actuator_target;
    const char *actuator_action;
    const char *ascii_art[VIEWPORT_HEIGHT];
} scene_def_t;

static const scene_def_t SCENES[5] = {
    {
        "sprout",
        "sprout",
        84,
        {14, 18, 42, 46},
        "mister",
        "on",
        {
            "+--------------------------------+",
            "| . . . . . . . . . . . . . . . .|",
            "| . . . . . \\   / . . . . . . . .|",
            "| . . . . . (o o) . . . . . . . .|",
            "| . . . . . . | . . . . . . . . .|",
            "| . . . . . . | . . . . . . . . .|",
            "| . . . ~~~~~~~~~~~ . . . . . . .|",
            "+--------------------------------+"
        }
    },
    {
        "indoor_plant",
        "indoor_plant",
        88,
        {12, 8, 44, 38},
        "light",
        "on",
        {
            "+--------------------------------+",
            "| . . . . : - = = - : . . . . . .|",
            "| . . . * # # @ @ # # * . . . . .|",
            "| . . * # [TARGET OBJECT] # * . .|",
            "| . . . * # # @ @ # # * . . . . .|",
            "| . . . . : - = = - : . . . . . .|",
            "| . . . . [___POT___] . . . . . .|",
            "+--------------------------------+"
        }
    },
    {
        "bell_pepper",
        "bell_pepper",
        91,
        {16, 12, 48, 44},
        "fan",
        "high",
        {
            "+--------------------------------+",
            "| . . . . . . || . . . . . . . . |",
            "| . . . . . /----\\ . . . . . . . |",
            "| . . . . (  PEPPER ) . . . . . .|",
            "| . . . .  \\______/ . . . . . . .|",
            "| . . . . . . . . . . . . . . . .|",
            "| . . . . . . . . . . . . . . . .|",
            "+--------------------------------+"
        }
    },
    {
        "ladybug",
        "ladybug",
        79,
        {20, 22, 36, 38},
        "buzzer",
        "on",
        {
            "+--------------------------------+",
            "| . . . . . \\ / . . . . . . . . .|",
            "| . . . . . (o) . . . . . . . . .|",
            "| . . . . / *|* \\ . . . . . . . .|",
            "| . . . . ( *|* ) . . . . . . . .|",
            "| . . . . \\__v__/ . . . . . . . .|",
            "| . . . . . . . . . . . . . . . .|",
            "+--------------------------------+"
        }
    },
    {
        "lampshade",
        "lampshade",
        85,
        {18, 10, 46, 40},
        "light",
        "on",
        {
            "+--------------------------------+",
            "| . . . . /======\\ . . . . . . . |",
            "| . . .  /  LAMP  \\ . . . . . . .|",
            "| . . . /==========\\ . . . . . . |",
            "| . . . . . . || . . . . . . . . |",
            "| . . . . . . || . . . . . . . . |",
            "| . . . . . /====\\ . . . . . . . |",
            "+--------------------------------+"
        }
    }
};

/* Application State */
static uint8_t g_inbox[N8_MSG_MAX] __attribute__((aligned(4)));
static int32_t g_scene_idx = 1; /* Default: indoor_plant */
static int32_t g_captured = 0;
static int32_t g_classified = 0;
static char g_cog_text[N8_MODEL_MAX_BYTES + 1];
static int32_t g_cog_status = 1; /* 1: idle; 0: reply ready; negative: error */

/* Volatile Frame Buffer (Purged after saccade extraction) */
static uint8_t g_volatile_dma[64 * 64];

uint8_t *image_inbox(void) { return g_inbox; }
N8_EXPORT(n8_inbox) int32_t n8_inbox(void) { return (int32_t)(uintptr_t)g_inbox; }

static void purge_volatile_dma(void)
{
    memset(g_volatile_dma, 0, sizeof(g_volatile_dma));
    const char notice[] = "privacy: volatile DMA purged, 0 raw pixels persisted\n";
    n8_log(notice, (int32_t)strlen(notice));
}

N8_EXPORT(n8_init) int32_t n8_init(void)
{
    g_scene_idx = 1;
    g_captured = 0;
    g_classified = 0;
    g_cog_status = 1;
    g_cog_text[0] = '\0';
    purge_volatile_dma();
    return 0;
}

static void handle_probe(void)
{
    const char resp[] = "cam sensor=UnoQ-QRB2210-Cam pid=0x2210 view=72 resolution=64x64 fps=5 status=ready";
    n8_reply_str(resp);
}

static void handle_scene(const uint8_t *p, int32_t n)
{
    if (n <= 0) {
        n8_reply_str("ERR missing scene index (0..4)");
        return;
    }
    int idx = p[0] - '0';
    if (idx < 0 || idx > 4) {
        n8_reply_str("ERR scene out of range (0..4)");
        return;
    }
    g_scene_idx = idx;
    g_captured = 0;
    g_classified = 0;

    char resp[64];
    int at = 0;
    n8_put(resp, &at, sizeof(resp), "ok scene=");
    n8_put(resp, &at, sizeof(resp), SCENES[g_scene_idx].name);
    n8_reply_str(resp);
}

static void handle_capture(void)
{
    /* Simulate camera frame ingestion into volatile DMA buffer */
    for (size_t i = 0; i < sizeof(g_volatile_dma); i++) {
        g_volatile_dma[i] = (uint8_t)(0x80 + (i & 0x1F));
    }
    g_captured = 1;

    /* Enforce Zero-Raw-Image-Persistence rule: purge volatile DMA immediately */
    purge_volatile_dma();

    char resp[96];
    int at = 0;
    n8_put(resp, &at, sizeof(resp), "ok captured scene=");
    n8_put(resp, &at, sizeof(resp), SCENES[g_scene_idx].name);
    n8_put(resp, &at, sizeof(resp), " (volatile DMA purged)");
    n8_reply_str(resp);
}

static void handle_classify(void)
{
    if (!g_captured) {
        handle_capture();
    }
    g_classified = 1;

    const scene_def_t *s = &SCENES[g_scene_idx];
    char resp[128];
    int at = 0;
    n8_put(resp, &at, sizeof(resp), "class=");
    n8_put(resp, &at, sizeof(resp), s->label);
    n8_put(resp, &at, sizeof(resp), " p=0.");
    n8_put_u(resp, &at, sizeof(resp), s->confidence_pct);
    n8_put(resp, &at, sizeof(resp), " ms=152 saccades=8");
    n8_reply_str(resp);
}

static void handle_status(void)
{
    const scene_def_t *s = &SCENES[g_scene_idx];
    char resp[192 + N8_MODEL_MAX_BYTES + 16];
    int at = 0;
    n8_put(resp, &at, sizeof(resp), "scene=");
    n8_put(resp, &at, sizeof(resp), s->name);
    n8_put(resp, &at, sizeof(resp), " class=");
    n8_put(resp, &at, sizeof(resp), s->label);
    n8_put(resp, &at, sizeof(resp), " p=0.");
    n8_put_u(resp, &at, sizeof(resp), s->confidence_pct);
    n8_put(resp, &at, sizeof(resp), " bbox=[");
    n8_put_u(resp, &at, sizeof(resp), s->bbox[0]);
    n8_put(resp, &at, sizeof(resp), ",");
    n8_put_u(resp, &at, sizeof(resp), s->bbox[1]);
    n8_put(resp, &at, sizeof(resp), ",");
    n8_put_u(resp, &at, sizeof(resp), s->bbox[2]);
    n8_put(resp, &at, sizeof(resp), ",");
    n8_put_u(resp, &at, sizeof(resp), s->bbox[3]);
    n8_put(resp, &at, sizeof(resp), "] privacy=zero_raw_persisted");
    /* the answer to the last cognitive turn (OP_COGNITIVE_TURN), once the broker has replied */
    if (g_cog_status == 0) {
        n8_put(resp, &at, sizeof(resp), " answer=");
        n8_put(resp, &at, sizeof(resp), g_cog_text);
    } else if (n8_model_pending()) {
        n8_put(resp, &at, sizeof(resp), " answer=pending");
    } else if (g_cog_status < 0) {
        n8_put(resp, &at, sizeof(resp), " answer=ERR");
    }
    n8_reply_str(resp);
}

static void handle_ascii_view(void)
{
    const scene_def_t *s = &SCENES[g_scene_idx];
    char buf[1024];
    int at = 0;

    n8_put(buf, &at, sizeof(buf), "--- na8ve-os Vision & Neural Perception ---\n");
    n8_put(buf, &at, sizeof(buf), "Frame: 64x64 QVGA Grayscale Viewport\n");

    for (int r = 0; r < VIEWPORT_HEIGHT; r++) {
        n8_put(buf, &at, sizeof(buf), s->ascii_art[r]);
        n8_put(buf, &at, sizeof(buf), "\n");
    }

    n8_put(buf, &at, sizeof(buf), "Detection: label=\"");
    n8_put(buf, &at, sizeof(buf), s->label);
    n8_put(buf, &at, sizeof(buf), "\" confidence=0.");
    n8_put_u(buf, &at, sizeof(buf), s->confidence_pct);
    n8_put(buf, &at, sizeof(buf), " bbox=[");
    n8_put_u(buf, &at, sizeof(buf), s->bbox[0]);
    n8_put(buf, &at, sizeof(buf), ",");
    n8_put_u(buf, &at, sizeof(buf), s->bbox[1]);
    n8_put(buf, &at, sizeof(buf), ",");
    n8_put_u(buf, &at, sizeof(buf), s->bbox[2]);
    n8_put(buf, &at, sizeof(buf), ",");
    n8_put_u(buf, &at, sizeof(buf), s->bbox[3]);
    n8_put(buf, &at, sizeof(buf), "]\n");
    n8_put(buf, &at, sizeof(buf), "Cognition: Event metadata routed to cortex-mvp (pVM #1)\n");
    n8_put(buf, &at, sizeof(buf), "Policy: Zero raw pixels persisted or transmitted.");

    n8_reply_str(buf);
}

static void handle_cognitive_turn(void)
{
    if (n8_model_pending()) {
        n8_reply_str("ERR busy");
        return;
    }

    const scene_def_t *s = &SCENES[g_scene_idx];
    char prompt[128];
    int at = 0;
    n8_put(prompt, &at, sizeof(prompt), "The camera sees ");
    n8_put(prompt, &at, sizeof(prompt), s->label);
    n8_put(prompt, &at, sizeof(prompt), ". What is it?");

    int32_t rc = n8_model_request(prompt, at, 32);
    if (rc != 0) {
        n8_reply_str("ERR model broker queue failed");
        return;
    }

    g_cog_status = -1; /* In-flight */
    n8_reply_str("ok queued");
}

static void handle_actuate(void)
{
    const scene_def_t *s = &SCENES[g_scene_idx];
    char cmd[128];
    int at = 0;
    n8_put(cmd, &at, sizeof(cmd), "act target=");
    n8_put(cmd, &at, sizeof(cmd), s->actuator_target);
    n8_put(cmd, &at, sizeof(cmd), " state=");
    n8_put(cmd, &at, sizeof(cmd), s->actuator_action);
    n8_put(cmd, &at, sizeof(cmd), " proposed_by=image-app");

    /* Dispatch proposal to Core 0 Actuator Safety Table */
    n8_ipc_send(0, N8_OP_ACTUATE, cmd, at);

    char resp[128];
    int r_at = 0;
    n8_put(resp, &r_at, sizeof(resp), "ok proposed ");
    n8_put(resp, &r_at, sizeof(resp), cmd);
    n8_reply_str(resp);
}

N8_EXPORT(n8_on_message) int32_t n8_on_message(int32_t from, int32_t op, int32_t n)
{
    /* Handle Model Broker Reply */
    if (from == N8_MODEL_BROKER && op == N8_MODEL_REPLY) {
        int32_t parsed = n8_model_parse(g_inbox, n, g_cog_text, sizeof(g_cog_text));
        if (parsed >= 0) {
            g_cog_status = 0; /* Success */
            n8_log("image-app: cognitive turn response received\n", 44);
        } else {
            g_cog_status = parsed;
            n8_log("image-app: cognitive turn failed\n", 33);
        }
        return 0;
    }

    /* Standard Command Dispatch */
    switch (op) {
        case N8_OP_PING:
            n8_reply_str("pong image-app");
            break;
        case OP_PROBE:
            handle_probe();
            break;
        case OP_SCENE:
            handle_scene(g_inbox, n);
            break;
        case OP_CAPTURE:
            handle_capture();
            break;
        case OP_CLASSIFY:
            handle_classify();
            break;
        case OP_STATUS:
            handle_status();
            break;
        case OP_ASCII_VIEW:
            handle_ascii_view();
            break;
        case OP_COGNITIVE_TURN:
            handle_cognitive_turn();
            break;
        case OP_ACTUATE:
            handle_actuate();
            break;
        default:
            n8_reply_str("ERR unknown op");
            break;
    }
    return 0;
}
