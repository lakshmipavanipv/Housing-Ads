# Ring QA Portal

A local web portal for bulk QA of electronic rings over Bluetooth. Every result is saved against the ring's
Bluetooth ID (MAC address), with a timestamp, the tester's name and a batch name. The Home page shows the
batch reports.

## Install (Windows laptop, one time)
1. Install Python 3.11+ from python.org and tick "Add Python to PATH".
2. Open a terminal in this folder (`ring-qa-portal`) and run:
   ```
   pip install -r requirements.txt
   ```

## 30 rings at once: USB ESP32 bridge boards
Windows' own Bluetooth can only hold a few rings at a time, so the portal can use ESP32 boards on a USB hub
as separate Bluetooth radios instead. **Each board holds up to 9 rings (an ESP32 hardware limit): 3 boards = 27 rings,
4 boards = 36.**
1. Plug the ESP32 boards into the USB hub. Use a powered hub.
2. Double-click **`flash_bridges.bat`**, which is needed once per board. It downloads the tools, asks which ESP32 type you
   have, and flashes `firmware/rqa_bridge` onto every board it finds. If a board fails, hold its **BOOT** button and
   run it again.
3. Double-click **`start_portal.bat`**. It installs the Python packages, starts the portal with the boards and opens
   the browser.
4. Check the **Connection** page: each board should show its COM port and **Connected**, with rings 0 / 9.

Rings fill the boards in order: board 1 (lowest COM port) until full, then board 2, then board 3. Each ring goes to
the first board that heard it in the last search, and a ring is only ever connected to one board.
If a board blinks but never shows a COM port, its USB cable is charge-only - use a data cable.
ESP32-C3 boards have small antennas: keep the rings within ~30 cm of the boards and turn off the Bluetooth of any
phone paired with the rings.

## Run (other modes)
```
python server.py                     (ESP32 USB boards if plugged in, else the laptop's own Bluetooth)
python server.py --backend dongles   (ESP32 USB boards only)
python server.py --backend local     (laptop's own Bluetooth only)
```
Open **http://localhost:8000** in Chrome or Edge.

To try it without any rings, start the simulator with 30 virtual rings. In it, ring 7 does not charge,
ring 13's HR sensor is dead and ring 21 will not connect. `--speed 30` makes one hour pass in two minutes:
```
python server.py --backend mock --speed 30
```

## Workflow per batch
1. Enter **Batch name** and **Tester** at the top. They are remembered between sessions.
2. **Connection**: check that "Local laptop Bluetooth" is selected, set the number of rings to test, and check
   the ring-model UUIDs.
3. **Bluetooth**: open the charge-case lids, click **Search**, then **Connect All**. Use **Buzz** on a row (vibration +
   screen blinking until **Stop**) to find a ring physically, and mark ✓/✗ whether you saw it. Click **Save Results**.
4. **Ring Battery**: click **Run Stage**. Every ring is pinged every minute. The tab shows the estimated time to 100 %,
   the time each ring reached 100 % and the variance against the estimate. Click **Save Results** when done.
5. **Time**: enter a time zone (e.g. `+05:30`) and a time shift, then click **Apply to all rings & verify**.
6. **Modes**: click each mode in the column header (Time, Counter, Steps, HR, SpO2, Sleep, Battery, Switch Off,
   Switch On) to switch all rings at once.
7. **Count / Steps / HR / SpO2 / HRV / Sleep**: click **Run Stage**. Rings are pinged every 10 s, with a live trend
   line and an average for each ring.
8. **Home**: shows each batch's PASS/FAIL counts per stage, a per-ring matrix (**View**) and a **CSV** export.

Rows turn red on FAIL. Buzz the ring to find it and set it aside.

## Ring model (UUID variables)
All BLE details live in `profiles/<model>.json` and can be edited on the **Connection** page. That page has
service/characteristic UUIDs, read/write/notify, the data parser, command bytes (mode, power, vibration, OLED)
and the PASS/FAIL rules and timings. Use **Save as new model** for another ring model.
`body_and_soul.json` ships with **placeholder UUIDs**, except battery (standard 0x180F/0x2A19). Fill in the real
values from the Body & Soul app before testing real rings.

## Notes
- Windows' Bluetooth stack can hold only a limited number of simultaneous connections (often about 7). Use the ESP32 boards.
- Results are stored in `qa.db` (SQLite) in this folder.
- Unit tests: `python -m pytest tests`
