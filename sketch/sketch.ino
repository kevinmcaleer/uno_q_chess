// Shows the computer's last move on the UNO Q LED matrix.
// Python sends a whole 8x13 frame through the Bridge: columns 0-7 are the
// board files a-h, row 0 is rank 8. The from-square is dim, the to-square bright.

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <vector>

Arduino_LED_Matrix matrix;

const uint8_t FRAME_SIZE = 8 * 13;
uint8_t frame[FRAME_SIZE] = {0};

void draw(std::vector<uint8_t> newFrame) {
    size_t len = min(newFrame.size(), (size_t)FRAME_SIZE);
    memcpy(frame, newFrame.data(), len);
}

void setup() {
    matrix.begin();
    matrix.setGrayscaleBits(3);   // brightness 0-7
    matrix.clear();
    Bridge.begin();
    Bridge.provide("draw", draw);
}

void loop() {
    matrix.draw(frame);
    delay(10);
}
