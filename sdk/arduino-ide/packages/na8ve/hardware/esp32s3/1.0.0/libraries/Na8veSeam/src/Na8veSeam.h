/* libraries/Na8veSeam/src/Na8veSeam.h - Metadata-Only Sensor Afferent Seam */
#ifndef Na8veSeam_h
#define Na8veSeam_h

#include <Arduino.h>

class Na8veSeamClass {
public:
    /* Read latest metadata-only sensor subject ("device", "greenhouse", "tank", "door") */
    int32_t read(const char *subject, char *json_out, size_t cap) {
        if (!subject || !json_out || cap == 0) return -1;
        char req[128];
        int at = 0;
        n8_put(req, &at, sizeof(req), "{\"tool\":\"readings_latest\",\"subject\":\"");
        n8_put(req, &at, sizeof(req), subject);
        n8_put(req, &at, sizeof(req), "\"}");
        return n8_tool(req, at, json_out, (int32_t)cap);
    }
};

static Na8veSeamClass Na8veSeam;

#endif /* Na8veSeam_h */

