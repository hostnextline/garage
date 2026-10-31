#!/bin/bash
# fake camera videos for test_vin.py (too big to keep in git): a door-sticker barcode, and a barcode that is not a VIN
cd "$(dirname "$0")"
for n in vin_civic not_vin; do ffmpeg -loglevel error -y -loop 1 -i $n.png -t 2 -r 10 -pix_fmt yuv420p $n.y4m; done
