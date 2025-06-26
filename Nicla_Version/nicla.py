import sys
import json
import time
import threading
import math
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QLabel, QGroupBox, QMessageBox
)
from PyQt5.QtCore import QTimer
import pyqtgraph as pg
import serial
import asyncio
from bleak import BleakClient
from pyqtgraph.opengl import GLViewWidget, GLMeshItem
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QSplitter
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog
from openpyxl import Workbook
from PyQt5.QtWidgets import QFileDialog
from openpyxl import Workbook

class NiclaWidget(QGroupBox):

    def __init__(self, title, port_default="COM10", ble_address=None, cube_color="red"):
        super().__init__(title)

        self.paused_at = None
        self.pause_duration = 0
        self.paused=False
        self.serial_conn = None
        self.running = False
        self.data_type = "Acceleration"
        self.buffer = []
        self.save = []
        self.cube_color = cube_color
        self.ble_client = None
        self.ble_uuid = "19b10000-5001-537e-4f6c-d104768a1214"
        self.connected = False
        self.ble_address = ble_address
        self.last_orientation = {"roll": 0, "pitch": 0, "yaw": 0}
        self.ble_loop = asyncio.new_event_loop()
        threading.Thread(target=self.ble_loop.run_forever, daemon=True).start()
        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_graph)

    def init_ui(self):
        layout = QVBoxLayout()
        # Connexion settings
        conn_layout = QHBoxLayout()
        #Comobox connexion mode
        self.conn_type = QComboBox()
        self.conn_type.addItems(["USB", "Bluetooth"])
        #Comobox connexion type
        self.conn_port = QComboBox()
        self.conn_port.addItems(["COM10", "COM11"])
        #Button connexion et disconnexion
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_device)
        #Label Connexion Status
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("background-color: red; color: white; padding: 2px;")
        #Label mode
        conn_layout.addWidget(QLabel("Mode:"))
        conn_layout.addWidget(self.conn_type)
        #Label Port
        conn_layout.addWidget(QLabel("Port:"))
        conn_layout.addWidget(self.conn_port)
        conn_layout.addWidget(self.connect_btn)
        conn_layout.addWidget(self.status_label)
        layout.addLayout(conn_layout)
        #reading type
        type_layout = QHBoxLayout()
        self.data_combo = QComboBox()
        self.data_combo.addItems(["Acceleration", "Gyroscope"])
        self.data_combo.currentTextChanged.connect(self.change_type)
        type_layout.addWidget(QLabel("Type:"))
        type_layout.addWidget(self.data_combo)
        layout.addLayout(type_layout)

        # Start / Stop
        ctrl_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.start_btn.clicked.connect(self.start_reading)
        self.stop_btn.clicked.connect(self.stop_reading)
        ctrl_layout.addWidget(self.start_btn)
        ctrl_layout.addWidget(self.stop_btn)
        layout.addLayout(ctrl_layout)

        # Graph
        graph_container = QHBoxLayout()
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setFixedWidth(900)
        self.plot_widget.setMinimumHeight(250)
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setLabel("left", "Value")
        self.plot_widget.setLabel("bottom", "Time (s)")
        self.plot_widget.enableAutoRange(axis='y', enable=True)
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.addLegend()
        # Checkbox layout
        checkbox_layout = QHBoxLayout()
        self.checkbox_x = QCheckBox("X")
        self.checkbox_y = QCheckBox("Y")
        self.checkbox_z = QCheckBox("Z")
        self.checkbox_x.setChecked(True)
        self.checkbox_y.setChecked(True)
        self.checkbox_z.setChecked(True)

        self.checkbox_x.stateChanged.connect(lambda: self.toggle_curve(0))
        self.checkbox_y.stateChanged.connect(lambda: self.toggle_curve(1))
        self.checkbox_z.stateChanged.connect(lambda: self.toggle_curve(2))

        checkbox_layout.addWidget(self.checkbox_x)
        checkbox_layout.addWidget(self.checkbox_y)
        checkbox_layout.addWidget(self.checkbox_z)
        layout.addLayout(checkbox_layout)

        self.curves = [
            self.plot_widget.plot(pen=pg.mkPen("r"), name="X"),
            self.plot_widget.plot(pen=pg.mkPen("g"), name="Y"),
            self.plot_widget.plot(pen=pg.mkPen("b"), name="Z")
        ]

        graph_container.addWidget(self.plot_widget)

        # 3D view
        self.gl_widget = GLViewWidget()
        self.gl_widget.setFixedSize(900, 200)
        self.gl_widget.opts['distance'] = 10
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.plot_widget)
        splitter.addWidget(self.gl_widget)
        splitter.setSizes([300, 300])

        layout.addWidget(splitter)
        # === Cube mesh ===
        verts = np.array([
            [1, 1, -1], [-1, 1, -1], [-1, -1, -1], [1, -1, -1],
            [1, 1, 1], [-1, 1, 1], [-1, -1, 1], [1, -1, 1]
        ])
        faces = np.array([
            [0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
            [1, 2, 6], [1, 6, 5], [0, 3, 7], [0, 7, 4]
        ])
        
        # Color Choice for each cube
        if hasattr(self, 'cube_color') and self.cube_color == "red":
            cube_color_rgba = [1, 0, 0, 1]
        else:
            cube_color_rgba = [0, 0, 1, 1]  

        colors = np.array([cube_color_rgba] * len(faces))

        # save for update
        self.original_verts = verts.copy()
        self.faces = faces
        self.colors = colors

        self.mesh = GLMeshItem(vertexes=verts, faces=faces, faceColors=colors, smooth=False, drawEdges=True)
        self.gl_widget.addItem(self.mesh)
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.toggle_pause)
        ctrl_layout.addWidget(self.pause_btn)
        self.pause_btn.setEnabled(False)

        self.setLayout(layout)

    def toggle_curve(self, index):

        if self.curves[index] is not None:
            visible = [self.checkbox_x.isChecked(), self.checkbox_y.isChecked(), self.checkbox_z.isChecked()]
            if visible[index]:
                self.curves[index].setVisible(True)
            else:
                self.curves[index].setVisible(False)
 
    def update_3d_orientation(self, roll, pitch, yaw):

        try:
            roll = math.radians(roll)
            pitch = math.radians(pitch)
            yaw = math.radians(yaw)

            #Rotation Matrix
            Rx = np.array([
                [1, 0, 0],
                [0, math.cos(roll), -math.sin(roll)],
                [0, math.sin(roll), math.cos(roll)]
            ])
            Ry = np.array([
                [math.cos(pitch), 0, math.sin(pitch)],
                [0, 1, 0],
                [-math.sin(pitch), 0, math.cos(pitch)]
            ])
            Rz = np.array([
                [math.cos(yaw), -math.sin(yaw), 0],
                [math.sin(yaw), math.cos(yaw), 0],
                [0, 0, 1]
            ])
            R = Rz @ Ry @ Rx

            rotated = np.dot(self.original_verts, R.T)

            self.mesh.setMeshData(vertexes=rotated, faces=self.faces, faceColors=self.colors)

        except Exception as e:
            print("❌ Orientation update error:", e)

    def toggle_pause(self):
        if self.running:
            # Pause
            self.running = False
            self.paused= True
            self.timer.stop()
            self.paused_at = time.time()
            self.pause_btn.setText("Resume")
            self.status_label.setText("Paused")
            self.status_label.setStyleSheet("background-color: orange; color: white; padding: 2px;")
        else:
            # Resume
            if self.paused_at:
                self.pause_duration += time.time() - self.paused_at
            self.running = True
            self.paused=False
            if self.conn_type.currentText() == "USB":
                threading.Thread(target=self.read_serial, daemon=True).start()
            elif self.conn_type.currentText() == "Bluetooth" and self.ble_client:
                threading.Thread(target=lambda: asyncio.run(self._ble_read(self.ble_client)), daemon=True).start()
            self.timer.start(10)
            self.pause_btn.setText("Pause")
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("background-color: green; color: white; padding: 2px;")

    def connect_device(self):

        if self.connected:
            self.running = False
            self.timer.stop()
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)

            if self.conn_type.currentText() == "USB" and self.serial_conn:
                self.serial_conn.close()
                self.serial_conn = None
            elif self.conn_type.currentText() == "Bluetooth" and self.ble_client:
                self.run_disconnect_ble()

            self.connected = False
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("background-color: red; color: white; padding: 2px;")
            self.connect_btn.setText("Connect")
            return

        # If not connected, we try to connect
        mode = self.conn_type.currentText()
        port = self.conn_port.currentText()

        if mode == "USB":
            try:
                self.serial_conn = serial.Serial(port, 115200, timeout=1)
                self.status_label.setText("Connected")
                self.status_label.setStyleSheet("background-color: green; color: white; padding: 2px;")
                self.connected = True
                self.connect_btn.setText("Disconnect")
                self.start_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
            except Exception as e:
                self.status_label.setText("Disconnected")
                print("❌ USB connection failed:", e)

        elif mode == "Bluetooth":
            self.connected = True
            threading.Thread(target=self.connect_ble, daemon=True).start()

    def run_disconnect_ble(self):
        if self.ble_loop and self.ble_loop.is_running():
            asyncio.run_coroutine_threadsafe(self.disconnect_ble(), self.ble_loop)

    async def disconnect_ble(self):
        if self.ble_client and self.ble_client.is_connected:
            try:
                await self.ble_client.disconnect()
                print("✅ BLE disconnected")
            except Exception as e:
                print("❌ BLE disconnection failed:", e)
        self.ble_client = None

    async def _ble_read(self, client):
        def handle_data(sender, data):
            try:
                msg = data.decode().strip()
                if msg.startswith("{") and msg.endswith("}"):
                    parsed = json.loads(msg)
                    t = time.time() - self.start_time - self.pause_duration
                    self.buffer.append((t, parsed))
                    self.save.append((t, parsed))
            except:
                pass

        await client.start_notify(self.ble_uuid, handle_data)
        while self.running:
            await asyncio.sleep(0.01)
        await client.stop_notify(self.ble_uuid)

    async def _connect_ble_async(self):
        if not self.ble_address:
            self.status_label.setText("Disconnected")
            print("⚠️ BLE address not set")
            return
        try:
            self.ble_client = BleakClient(self.ble_address)
            await self.ble_client.connect()
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("background-color: green; color: white;")
            self.connect_btn.setText("Disconnect")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            print(f"✅ Connected to BLE device at {self.ble_address}")
        except Exception as e:
            print("❌ BLE connection failed:", e)
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("background-color: red; color: white;")
    
    def connect_ble(self):
        asyncio.run(self._connect_ble_async())

    def change_type(self, value):
        self.data_type = value

    def start_reading(self):
        self.pause_btn.setEnabled(True) 
        self.running = True
        self.buffer = []
        self.save=[]
        self.start_time = time.time()
        if self.conn_type.currentText() == "USB":
            threading.Thread(target=self.read_serial, daemon=True).start()
        elif self.conn_type.currentText() == "Bluetooth" and self.ble_client:
            threading.Thread(target=lambda: asyncio.run(self._ble_read(self.ble_client)), daemon=True).start()
        self.timer.start(10)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_reading(self):
        if not self.running:
            if self.paused==True:
                self.pause_btn.setEnabled(False)
                self.pause_btn.setText("Pause")

                self.running = False
                self.timer.stop()

                if self.save:
                    response = QMessageBox.question(self, "Save Data", "Do you want to save the recorded data?",
                                                    QMessageBox.Yes | QMessageBox.No)
                    if response == QMessageBox.Yes:
                        self.save_to_csv()
                    self.save=[]

                self.status_label.setText("Connected")
                self.status_label.setStyleSheet("background-color: green; color: white; padding: 2px;")

                self.start_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
            else:
                return  
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("Pause")

        self.running = False
        self.timer.stop()


        if self.save:
            response = QMessageBox.question(self, "Save Data", "Do you want to save the recorded data?",
                                            QMessageBox.Yes | QMessageBox.No)
            if response == QMessageBox.Yes:
                self.save_to_csv()
            self.save=[]

        self.status_label.setText("Connected")
        self.status_label.setStyleSheet("background-color: green; color: white; padding: 2px;")

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def read_serial(self):
        while self.running:
            try:
                line = self.serial_conn.readline().decode().strip()
                if line.startswith('{') and line.endswith('}'):
                    data = json.loads(line)
                    t = time.time() - self.start_time - self.pause_duration
                    self.buffer.append((t, data))
                    self.save.append((t, data))
            except:
                pass

    def update_graph(self):
        keymap = {
            "Acceleration": ["ax", "ay", "az"],
            "Gyroscope": ["gx", "gy", "gz"]
        }
        keys = keymap[self.data_type]

        max_seconds = 5
        self.buffer = [(t, d) for t, d in self.buffer if t >= self.buffer[-1][0] - max_seconds]
        if not self.buffer:
            for curve in self.curves:
                curve.clear()
            return

        x = [t for t, _ in self.buffer]
        ys = [[], [], []]
        for _, data in self.buffer:
            for i, k in enumerate(keys):
                ys[i].append(data.get(k, 0))

        for i in range(3):
            self.curves[i].setData(x, ys[i])

        self.plot_widget.setXRange(x[0], x[-1], padding=0)

        latest_data = self.buffer[-1][1]
        if all(k in latest_data for k in ["roll", "pitch", "yaw"]):
            r = latest_data["roll"]
            p = latest_data["pitch"]
            y = latest_data["yaw"]
            self.update_3d_orientation(r, p, y)
            self.last_orientation = {"roll": r, "pitch": p, "yaw": y}

    def save_to_csv(self):
        if not self.save:
            return

        keys = ["timestamp", "ax", "ay", "az", "gx", "gy", "gz", "roll", "pitch", "yaw"]
        default_name = f"{self.title().replace(' ', '_')}_data.xlsx"

        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Excel File",
            default_name,
            "Excel Files (*.xlsx)",
            options=options
        )

        if not file_path:
            return

        if not file_path.endswith(".xlsx"):
            file_path += ".xlsx"

        wb = Workbook()
        ws = wb.active
        ws.title = "Nicla Data"

        ws.append(keys)

        for t, d in self.save:
            row = [t] + [d.get(k, "") for k in keys[1:]]
            ws.append(row)

        wb.save(file_path)
        print(f"💾 Excel file saved to {file_path}")

class MainApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nicla Dual Viewer")

        main_layout = QVBoxLayout()

        dual_layout = QHBoxLayout()
        self.nicla1 = NiclaWidget("Nicla 1 (Bleu)", port_default="COM10", ble_address="63:E8:45:79:A9:EB", cube_color="blue")
        self.nicla2 = NiclaWidget("Nicla 2 (Rouge)", port_default="COM11", ble_address="4D:14:4E:C0:2B:C8", cube_color="red")
        dual_layout.addWidget(self.nicla1)
        dual_layout.addWidget(self.nicla2)
        main_layout.addLayout(dual_layout)

        control_layout = QHBoxLayout()
        self.start_both_btn = QPushButton("Start Both")
        self.stop_both_btn = QPushButton("Stop Both")
        self.stop_both_btn.clicked.connect(self.stop_both)
        self.start_both_btn.clicked.connect(self.start_both)
        control_layout.addWidget(self.stop_both_btn)
        control_layout.addWidget(self.start_both_btn)
        main_layout.addLayout(control_layout)

        self.setLayout(main_layout)

    def start_both(self):
        if not self.nicla1.connected or not self.nicla2.connected:
            QMessageBox.warning(self, "Connection Required", "Both Nicla must be connected first.")
            return
        self.nicla1.start_reading()
        self.nicla2.start_reading()
        self.start_both_btn.setEnabled(False)
        self.stop_both_btn.setEnabled(True)

    def stop_both(self):
        if not (self.nicla1.running or self.nicla2.running):
            return

        if self.nicla1.running:
            self.nicla1.running = False
            self.nicla1.timer.stop()
            self.nicla1.pause_btn.setEnabled(False)
            self.nicla1.pause_btn.setText("Pause")
            self.nicla1.start_btn.setEnabled(True)
            self.nicla1.stop_btn.setEnabled(False)

        if self.nicla2.running:
            self.nicla2.running = False
            self.nicla2.timer.stop()
            self.nicla2.pause_btn.setEnabled(False)
            self.nicla2.pause_btn.setText("Pause")
            self.nicla2.start_btn.setEnabled(True)
            self.nicla2.stop_btn.setEnabled(False)

        if not self.nicla1.save and not self.nicla2.save:
            return
        self.start_both_btn.setEnabled(True)
        self.stop_both_btn.setEnabled(False)

        response = QMessageBox.question(
            self,
            "Save Data",
            "Do you want to save the recorded data from both Nicla?",
            QMessageBox.Yes | QMessageBox.No
        )
        if response != QMessageBox.Yes:
            self.nicla1.save = []
            self.nicla2.save = []
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save Combined Excel File", "", "Excel Files (*.xlsx)")
        if not path:
            return

        if not path.endswith(".xlsx"):
            path += ".xlsx"

        wb = Workbook()
        ws = wb.active
        ws.title = "Nicla Data"
        headers = ["timestamp", "ax", "ay", "az", "gx", "gy", "gz", "roll", "pitch", "yaw", "source"]
        ws.append(headers)

        for label, data in [("Nicla 1", self.nicla1.save), ("Nicla 2", self.nicla2.save)]:
            for t, d in data:
                row = [
                    t,
                    d.get("ax", 0),
                    d.get("ay", 0),
                    d.get("az", 0),
                    d.get("gx", 0),
                    d.get("gy", 0),
                    d.get("gz", 0),
                    d.get("roll", 0),
                    d.get("pitch", 0),
                    d.get("yaw", 0),
                    label
                ]
                ws.append(row)

        try:
            wb.save(path)
            print(f"💾 Combined data saved to {path}")
        except Exception as e:
            print(f"❌ Failed to save combined file: {e}")

        self.nicla1.save = []
        self.nicla2.save = []

if __name__ == "__main__":

    app = QApplication(sys.argv)
    main_win = MainApp()
    main_win.nicla1.start_btn.setEnabled(False)
    main_win.nicla1.stop_btn.setEnabled(False)
    main_win.nicla2.start_btn.setEnabled(False)
    main_win.nicla2.stop_btn.setEnabled(False)
    main_win.resize(800, 600)
    main_win.show()
    sys.exit(app.exec_())
