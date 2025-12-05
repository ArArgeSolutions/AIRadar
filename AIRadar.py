import os
import requests
import time
import qt
import ctk 
import slicer
import json
import uuid
import random
import tempfile
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

# ==============================================================================
# 1. MODULE DEFINITION
# ==============================================================================

class AIRadar(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "AIRadar Extension" 
        self.parent.categories = ["MONAI", "Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Ar ARGE"] 
        self.parent.helpText = """
        Professional client for MONAI Label server integration and HoloLens connectivity.
        """
        self.parent.acknowledgementText = """Developed by Ar ARGE for clinical integration."""

# ==============================================================================
# 2. WIDGET / UI
# ==============================================================================

class AIRadarWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self.device_code = str(random.randint(1000, 9999))
        self.session_id = str(uuid.uuid4())[:8] 
        self.timer = qt.QTimer()
        self.is_logged_in = False
        self.current_sis_id = None 

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = AIRadarLogic()

        # --- 1. AUTHENTICATION PANEL ---
        self.authPanel = slicer.qMRMLCollapsibleButton()
        self.authPanel.text = "1. DEVICE PAIRING & AUTHENTICATION"
        self.layout.addWidget(self.authPanel)
        authLayout = qt.QFormLayout(self.authPanel)

        #self.apiLine = qt.QLineEdit("https://airadar.uzem.afsu.edu.tr")
        self.apiLine = qt.QLineEdit("http://localhost:3005")
        authLayout.addRow("API Endpoint:", self.apiLine)
        
        self.monaiLine = qt.QLineEdit("http://34.204.196.213:8000")
        authLayout.addRow("MONAI Server:", self.monaiLine)

        self.codeDisplay = qt.QLabel(self.device_code)
        self.codeDisplay.setAlignment(qt.Qt.AlignCenter)
        self.codeDisplay.setStyleSheet("font-size: 40px; font-weight: bold; color: #2196F3; border: 3px dashed #2196F3; padding: 10px; margin: 10px;")
        authLayout.addRow(self.codeDisplay)

        self.instructionLabel = qt.QLabel("Please authenticate via the Web Portal using this code.")
        self.instructionLabel.setAlignment(qt.Qt.AlignCenter)
        authLayout.addRow(self.instructionLabel)

        self.statusLabel = qt.QLabel("Waiting for connection... ⏳")
        self.statusLabel.setAlignment(qt.Qt.AlignCenter)
        self.statusLabel.setStyleSheet("color: orange;")
        authLayout.addRow(self.statusLabel)

        # --- 2. SERVER PATIENT LIST (Hasta Listesi) ---
        self.patientsPanel = slicer.qMRMLCollapsibleButton()
        self.patientsPanel.text = "2. SUNUCU HASTA LİSTESİ"
        self.patientsPanel.enabled = False 
        self.layout.addWidget(self.patientsPanel)
        patientsLayout = qt.QVBoxLayout(self.patientsPanel)

        self.refreshPatientsBtn = qt.QPushButton("📂 Listeyi Getir/Yenile")
        patientsLayout.addWidget(self.refreshPatientsBtn)

        self.fileListWidget = qt.QListWidget()
        patientsLayout.addWidget(self.fileListWidget)

        self.loadToSlicerBtn = qt.QPushButton("🖥️ Sahnede Göster (Load)")
        self.loadToSlicerBtn.setStyleSheet("background-color: #3498db; color: white; font-weight: bold;")
        patientsLayout.addWidget(self.loadToSlicerBtn)
        
        self.fileListWidget.connect('itemDoubleClicked(QListWidgetItem*)', self.onLoadPatientClicked)
        self.loadToSlicerBtn.connect('clicked(bool)', self.onLoadPatientClicked)

        # --- 3. HOLOLENS CONTROL (Gözlük Kontrolü) ---
        self.holoPanel = slicer.qMRMLCollapsibleButton()
        self.holoPanel.text = "3. HOLOLENS KONTROLÜ"
        self.holoPanel.enabled = False
        self.layout.addWidget(self.holoPanel)
        holoLayout = qt.QFormLayout(self.holoPanel)

        self.ipInput = qt.QLineEdit()
        self.ipInput.text = "192.168.1.50" 
        holoLayout.addRow("HoloLens IP:", self.ipInput)

        self.viewOnHoloButton = qt.QPushButton("🥽 Seçileni Gözlükte Göster")
        self.viewOnHoloButton.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 10px;")
        holoLayout.addRow(self.viewOnHoloButton)

        # --- 4. MONAI DATASET MANAGEMENT ---
        self.appPanel = slicer.qMRMLCollapsibleButton()
        self.appPanel.text = "4. MONAI VERİ YÖNETİMİ (OPSİYONEL)"
        self.appPanel.enabled = False
        self.layout.addWidget(self.appPanel)
        appLayout = qt.QFormLayout(self.appPanel)

        self.userLabel = qt.QLabel("Active User: -")
        self.userLabel.setStyleSheet("font-weight: bold; color: #666;")
        appLayout.addRow(self.userLabel)

        self.serverImagesCombo = qt.QComboBox()
        self.serverImagesCombo.setToolTip("Available datasets on the MONAI server.")
        appLayout.addRow("MONAI Datasets:", self.serverImagesCombo)
        
        self.refreshBtn = qt.QPushButton("Refresh MONAI List")
        appLayout.addRow(self.refreshBtn)
        
        self.downloadBtn = qt.QPushButton("DOWNLOAD MONAI CASE")
        appLayout.addRow(self.downloadBtn)
        
        self.deleteBtn = qt.QPushButton("Delete Resource")
        self.deleteBtn.setStyleSheet("color: #d9534f; font-weight: bold;")
        appLayout.addRow(self.deleteBtn)

        # --- 5. UPLOAD PANEL ---
        self.uploadPanel = slicer.qMRMLCollapsibleButton()
        self.uploadPanel.text = "5. UPLOAD NEW CASE (MONAI)"
        self.uploadPanel.enabled = False 
        self.layout.addWidget(self.uploadPanel)
        uploadLayout = qt.QFormLayout(self.uploadPanel)

        self.imageIdLine = qt.QLineEdit()
        self.imageIdLine.setPlaceholderText("Case ID / Patient Name")
        uploadLayout.addRow("Case ID:", self.imageIdLine)

        self.imageSelector = slicer.qMRMLNodeComboBox()
        self.imageSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.imageSelector.selectNodeUponCreation = True
        self.imageSelector.addEnabled = False
        self.imageSelector.removeEnabled = False
        self.imageSelector.noneEnabled = True
        self.imageSelector.showHidden = False
        self.imageSelector.setMRMLScene(slicer.mrmlScene)
        uploadLayout.addRow("Source Image:", self.imageSelector)

        self.labelSelector = slicer.qMRMLNodeComboBox()
        self.labelSelector.nodeTypes = ["vtkMRMLLabelMapVolumeNode", "vtkMRMLSegmentationNode"]
        self.labelSelector.selectNodeUponCreation = True
        self.labelSelector.addEnabled = False
        self.labelSelector.removeEnabled = False
        self.labelSelector.noneEnabled = True
        self.labelSelector.showHidden = False
        self.labelSelector.setMRMLScene(slicer.mrmlScene)
        appLayout.addRow("Segmentation:", self.labelSelector)

        self.publicModeCheckBox = qt.QCheckBox("Mark as Public Dataset")
        uploadLayout.addRow(self.publicModeCheckBox)

        self.isNewPatientCheckBox = qt.QCheckBox("New Case Label Image Upload")
        uploadLayout.addRow(self.isNewPatientCheckBox)

        self.uploadBtn = qt.QPushButton("UPLOAD TO SERVER")
        self.uploadBtn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; height: 40px;")
        uploadLayout.addRow(self.uploadBtn)

        self.layout.addStretch(1)

        # INITIALIZATION
        self.registerDevice()
        self.timer.timeout.connect(self.checkLoginStatus)
        self.timer.start(2000)

        # SIGNAL CONNECTIONS
        self.refreshBtn.connect('clicked(bool)', self.onRefreshList)
        self.uploadBtn.connect('clicked(bool)', self.onUpload)
        self.deleteBtn.connect('clicked(bool)', self.onDelete)
        self.downloadBtn.connect('clicked(bool)', self.onDownload)
        self.serverImagesCombo.currentTextChanged.connect(self.onImageSelected)
        self.publicModeCheckBox.connect('toggled(bool)', self.onPublicToggled)
        
        # YENİ SİNYALLER (Hasta Listesi ve HoloLens)
        self.refreshPatientsBtn.connect('clicked(bool)', self.onRefreshPatientsClicked)
        self.viewOnHoloButton.connect('clicked(bool)', self.onViewOnHoloClicked)

    # --- UI OPERATIONS ---

    def registerDevice(self):
        try:
            base_url = self.apiLine.text.rstrip('/')
            url = f"{base_url}/api/start-session/{self.device_code}"
            requests.get(url, timeout=5, verify=False)
        except Exception as e: 
            self.statusLabel.setText("Connection Error!")
            print(f"Auth Error: {e}")

    def checkLoginStatus(self):
        if self.is_logged_in: 
            self.timer.stop()
            return
        try:
            base_url = self.apiLine.text.rstrip('/')
            url = f"{base_url}/api/check-session/{self.device_code}"
            resp = requests.get(url, timeout=5, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") and data.get("status") == "LOGGED_IN":
                    self.unlockApp(data.get("user"), data.get("sis_id"))
        except: pass

    def unlockApp(self, name, sis_id):
        self.is_logged_in = True
        self.current_sis_id = sis_id
        self.session_id = sis_id 
        self.timer.stop()

        self.statusLabel.setText("✅ AUTHENTICATED")
        self.statusLabel.setStyleSheet("color: green; font-weight: bold;")
        self.codeDisplay.setStyleSheet("font-size: 40px; font-weight: bold; color: white; background: green; border: 3px solid green; padding: 10px;")
        
        self.authPanel.enabled = False
        self.appPanel.enabled = True
        self.uploadPanel.enabled = True
        self.patientsPanel.enabled = True
        self.holoPanel.enabled = True
        
        self.userLabel.setText(f"Operator: {name} | ID: {sis_id}")
        self.userLabel.setStyleSheet("color: green; font-weight: bold;")
        self.onRefreshList() # MONAI listesini de çekmeyi dener

    def onPublicToggled(self, checked):
        if checked: self.publicModeCheckBox.setStyleSheet("color: #d9534f; font-weight: bold;")
        else: self.publicModeCheckBox.setStyleSheet("")

    def onRefreshList(self):
        # Eski MONAI listesi (Altta kalan panel için)
        if not self.session_id: 
            self.statusLabel.setText("Please login first.")
            return
        self.serverImagesCombo.clear()
        self.statusLabel.setText("Syncing MONAI...")
        slicer.app.processEvents() 
        images = self.logic.fetch_all_images(self.monaiLine.text, current_user_session_id=self.session_id)
        if images: 
            self.serverImagesCombo.addItems(images)
            self.statusLabel.setText(f"{len(images)} MONAI datasets found.")
        else:
            self.statusLabel.setText("No MONAI datasets found.")

    def onRefreshPatientsClicked(self):
        # YENİ: Backend Hasta Listesini Çek
        self.fileListWidget.clear()
        
        # Eğer giriş yapılmamışsa uyarı ver
        if not self.current_sis_id:
            self.statusLabel.setText("Lütfen önce giriş yapınız!")
            return

        self.statusLabel.setText("Hasta listesi çekiliyor...")
        slicer.app.processEvents()

        # [cite_start]Logic üzerinden çek (user_tag parametresini ekledik) [cite: 367]
        patients = self.logic.fetch_backend_patients(self.apiLine.text, self.current_sis_id)
        
        if patients:
            for p in patients:
                # Ekranda isim göster, arkada key (ID) sakla
                item = qt.QListWidgetItem(p.get('name', 'Unknown'))
                item.setData(qt.Qt.UserRole, p.get('key')) 
                self.fileListWidget.addItem(item)
            self.statusLabel.setText(f"{len(patients)} hasta listelendi.")
        else:
            self.fileListWidget.addItem("Dosya bulunamadı veya liste boş.")
            self.statusLabel.setText("Liste boş.")

    def onViewOnHoloClicked(self):
        # YENİ: Seçileni İndir -> Yükle -> Gözlüğe Gönder
        selectedItems = self.fileListWidget.selectedItems()
        if not selectedItems:
            self.statusLabel.setText("Lütfen listeden bir dosya seçin!")
            return
            
        ip = self.ipInput.text
        if not ip:
            self.statusLabel.setText("HoloLens IP giriniz.")
            return

        imageKey = selectedItems[0].data(qt.Qt.UserRole)
        imageName = selectedItems[0].text()

        self.statusLabel.setText(f"İndiriliyor: {imageName}...")
        slicer.app.processEvents()

        # 1. Dosyayı İndir ve Slicer'a Yükle (Sahneyi temizler)
        if self.logic.download_and_load_patient(self.apiLine.text, imageKey):
            
            # 2. Volume Rendering Aktif Et
            self.statusLabel.setText("3D Görüntü (VR) hazırlanıyor...")
            self.logic.setup_volume_rendering()
            
            # 3. HoloLens'e Bağlan
            self.statusLabel.setText(f"HoloLens'e ({ip}) bağlanıyor...")
            success, msg = self.logic.connect_to_hololens(ip)
            self.statusLabel.setText(msg)
        else:
            self.statusLabel.setText("İndirme başarısız!")

    def onLoadPatientClicked(self):
        """Seçilen hastayı ve segmentasyonunu Slicer ekranlarına yükler"""
        selectedItems = self.fileListWidget.selectedItems()
        if not selectedItems:
            self.statusLabel.setText("Lütfen listeden bir dosya seçin!")
            return
            
        imageKey = selectedItems[0].data(qt.Qt.UserRole)
        imageName = selectedItems[0].text()

        # Kullanıcı ID'si giriş yaparken kaydedilmişti (self.current_sis_id)
        if not self.current_sis_id:
             self.statusLabel.setText("Oturum bilgisi eksik!")
             return

        self.statusLabel.setText(f"Veriler indiriliyor: {imageName}...")
        slicer.app.processEvents()

        # --- GÜNCELLENEN KISIM: Yeni fonksiyonu çağırıyoruz ---
        success, msg = self.logic.download_patient_with_seg(
            self.apiLine.text, 
            imageKey, 
            self.current_sis_id # Label'ı bulmak için kullanıcının ID'sini gönderiyoruz
        )
        
        if success:
            self.statusLabel.setText(f"✅ Yüklendi: {imageName}")
            
            # 3D Görüntüyü ayarla
            self.logic.setup_volume_rendering()
            slicer.util.resetThreeDViews()
        else:
            self.statusLabel.setText(f"❌ Hata: {msg}")

    

    def onImageSelected(self, text):
        clean_name = text
        if text.startswith("public_"):
            clean_name = text[7:] 
        elif text.startswith(f"{self.current_sis_id}_"):
            clean_name = text[len(self.current_sis_id)+1:]
        self.imageIdLine.text = clean_name

    def onUpload(self):
        if not self.current_sis_id: return
        raw_name = self.imageIdLine.text
        if not raw_name or not self.labelSelector.currentNode():
            self.statusLabel.setText("Missing Inputs!")
            return
        is_public_checked = self.publicModeCheckBox.checked
        self.statusLabel.setText("Uploading...")
        slicer.app.processEvents()
        success, msg = self.logic.process_upload(
            server_url=self.monaiLine.text,
            raw_image_name=raw_name,
            is_public=is_public_checked,
            image_node=self.imageSelector.currentNode(),
            label_node=self.labelSelector.currentNode(),
            is_new_patient=self.isNewPatientCheckBox.checked,
            user_session_id=self.session_id,
            user_tag=self.current_sis_id
        )
        self.statusLabel.setText(msg)
        if success: self.onRefreshList()

    def onDownload(self):
        image_id = self.serverImagesCombo.currentText
        if not image_id: return
        selected_folder = qt.QFileDialog.getExistingDirectory(self.parent, "Select Download Destination")
        if not selected_folder: return 
        self.statusLabel.setText(f"Downloading...\n{image_id}")
        slicer.app.processEvents()
        success, msg = self.logic.download_image_and_label(
            server_url=self.monaiLine.text, 
            image_id=image_id, 
            user_tag=self.current_sis_id,
            target_folder=selected_folder
        )
        if success:
            self.statusLabel.setText("✅ Completed")
            self.statusLabel.setStyleSheet("color: green;")
            qt.QMessageBox.information(slicer.util.mainWindow(), "Download Complete", f"Dataset saved:\n{selected_folder}")
        else:
            self.statusLabel.setText("❌ Failed")
            self.statusLabel.setStyleSheet("color: red;")
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Download Error", msg)

    def onDelete(self):
        full_name = self.serverImagesCombo.currentText
        if not full_name: return
        is_public = full_name.startswith("public_") or "public" in full_name.lower()
        msgBox = qt.QMessageBox()
        msgBox.setIcon(qt.QMessageBox.Warning)
        msgBox.setWindowTitle("Delete Resource")
        msgBox.setText(f"Select deletion scope for '{full_name}':")
        btnLabel = msgBox.addButton("Delete Segmentation Only", qt.QMessageBox.ActionRole)
        btnImage = msgBox.addButton("Delete Entire Case (Image+Seg)", qt.QMessageBox.ActionRole)
        btnCancel = msgBox.addButton("Cancel", qt.QMessageBox.RejectRole)
        msgBox.exec_()
        delete_mode = None
        if msgBox.clickedButton() == btnLabel: delete_mode = "label"
        elif msgBox.clickedButton() == btnImage: delete_mode = "image"
        else: return 
        if delete_mode == "image":
            confirm = qt.QMessageBox.question(slicer.util.mainWindow(), "Confirm Delete", "Delete permanently?", qt.QMessageBox.Yes | qt.QMessageBox.No)
            if confirm == qt.QMessageBox.No: return
        self.statusLabel.setText("Deleting...")
        slicer.app.processEvents()
        success, msg = self.logic.delete_resource(
            server_url=self.monaiLine.text,
            image_id=full_name,
            user_session_id=self.session_id, 
            delete_mode=delete_mode
        )
        if success:
            self.statusLabel.setText("✅ Deleted")
            self.statusLabel.setStyleSheet("color: green;")
            self.onRefreshList()
        else:
            self.statusLabel.setText("❌ Error")
            self.statusLabel.setStyleSheet("color: red;")
            qt.QMessageBox.critical(slicer.util.mainWindow(), "Error", msg)

# ==============================================================================
# 3. LOGIC
# ==============================================================================

class AIRadarLogic(ScriptedLoadableModuleLogic):
    
    MASTER_PUBLIC_SESSION_ID = "PUBLIC_SHARED_ACCESS_KEY_2025_V1" 
    ENDPOINT_DATASTORE = "/datastore/"
    ENDPOINT_IMAGE = "/datastore/image"
    ENDPOINT_LABEL = "/datastore/label"

    # --- NEW: BACKEND & HOLOLENS LOGIC ---
    
    def fetch_backend_patients(self, api_base_url, user_tag=None):
        """Backend sunucusundan hasta listesini çeker"""
        try:
            base_url = api_base_url.rstrip('/')
            url = f"{base_url}/slicer/patients"
            
            # Parametreleri hazırla: user_tag'i query string olarak ekliyoruz
            params = {}
            if user_tag:
                params['user_tag'] = user_tag

            # [cite_start]Verify=False SSL hatalarını önlemek için [cite: 358]
            response = requests.get(url, params=params, timeout=5, verify=False)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("patients", [])
            return []
        except Exception as e:
            print(f"Backend Fetch Error: {e}")
            return []

    def download_and_load_patient(self, api_base_url, image_key):
        """Backend'den resmi indirir, kaydeder ve Slicer'a yükler (Sahneyi Temizler)"""
        try:
            base_url = api_base_url.rstrip('/')
            downloadUrl = f"{base_url}/monailabel-datastore-image-download?image={image_key}&inline=1"
            
            print(f"Downloading from: {downloadUrl}")
            response = requests.get(downloadUrl, stream=True, verify=False)
            
            if response.status_code != 200:
                print(f"Download Error Code: {response.status_code}")
                return False

            tempDir = tempfile.gettempdir()
            localPath = os.path.join(tempDir, f"{image_key}.nii.gz")
            
            with open(localPath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # SAHNEYİ TEMİZLEME (Önemli!)
            slicer.mrmlScene.Clear(0) 
            
            loaded_node = slicer.util.loadVolume(localPath)
            if loaded_node:
                print(f"Loaded: {localPath}")
                return True
            return False
        except Exception as e:
            print(f"Download/Load Error: {e}")
            return False

    def download_patient_with_seg(self, api_base_url, image_key, user_tag):
        """Hem görüntüyü hem de segmentasyonu indirir ve üst üste bindirir."""
        try:
            base_url = api_base_url.rstrip('/')
            
            # 1. ANA GÖRÜNTÜYÜ İNDİR
            imgUrl = f"{base_url}/monailabel-datastore-image-download?image={image_key}&inline=1"
            print(f"Downloading Image: {imgUrl}")
            
            # Sahneyi Temizle
            slicer.mrmlScene.Clear(0)
            
            # Resmi indir ve kaydet
            resp_img = requests.get(imgUrl, stream=True, verify=False)
            if resp_img.status_code == 200:
                tempDir = tempfile.gettempdir()
                imgPath = os.path.join(tempDir, f"{image_key}_source.nii.gz")
                with open(imgPath, 'wb') as f:
                    for chunk in resp_img.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Resmi Slicer'a Yükle
                imgNode = slicer.util.loadVolume(imgPath)
                imgNode.SetName(f"{image_key}_Image")
            else:
                return False, "Resim indirilemedi."

            # 2. SEGMENTASYONU (LABEL) İNDİR (Opsiyonel)
            # Not: Label indirmek için user_tag (giriş yapan kullanıcı ID) gereklidir.
            lblUrl = f"{base_url}/monailabel-datastore-label-download?label={image_key}&tag={user_tag}&inline=1"
            print(f"Downloading Label: {lblUrl}")

            resp_lbl = requests.get(lblUrl, stream=True, verify=False)
            
            if resp_lbl.status_code == 200:
                lblPath = os.path.join(tempDir, f"{image_key}_label.nii.gz")
                with open(lblPath, 'wb') as f:
                    for chunk in resp_lbl.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Label'ı "LabelMap" olarak yükle
                lblNode = slicer.util.loadLabelVolume(lblPath)
                lblNode.SetName(f"{image_key}_Seg")
                
                # Renklendirme ve Görünürlük Ayarı
                # Label'ın otomatik olarak resmin üzerine oturması gerekir.
            else:
                print("Segmentasyon dosyası bulunamadı veya sunucu hatası (Bu normal olabilir).")

            return True, "Yüklendi"

        except Exception as e:
            print(f"Yükleme Hatası: {e}")
            return False, str(e)

    def setup_volume_rendering(self):
        """Yüklenen volume için 3D rendering ayarlarını yapar"""
        try:
            volRenLogic = slicer.modules.volumerendering.logic()
            volumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if volumeNode:
                displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(volumeNode)
                if displayNode:
                    displayNode.SetVisibility(True)
                    presets = volRenLogic.GetPresets()
                    preset = presets.GetItemByName("MR-Default")
                    if preset:
                        displayNode.GetVolumePropertyNode().Copy(preset)
                    slicer.util.resetThreeDViews()
        except Exception as e:
            print(f"Volume Rendering Error: {e}")

    def connect_to_hololens(self, ip_address):
        """Slicer VR modülünü kullanarak HoloLens'e bağlanır"""
        try:
            vrLogic = slicer.modules.virtualreality.logic()
            vrViewNode = vrLogic.GetVirtualRealityViewNode()
            if not vrViewNode:
                vrViewNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLVirtualRealityViewNode")
                vrLogic.SetVirtualRealityViewNode(vrViewNode)

            vrViewNode.SetRemotingAddress(ip_address)
            
            # Bağlantıyı sıfırla ve yeniden başlat
            if vrLogic.GetVirtualRealityConnected():
                vrLogic.SetVirtualRealityConnected(False)
            
            vrLogic.SetVirtualRealityConnected(True)
            return True, "✅ Connected to HoloLens!"
        except Exception as e:
            print(f"VR Connection Error: {e}")
            return False, f"VR Error: {e}"

    # --- EXISTING: MONAI LOGIC ---

    def fetch_all_images(self, url, current_user_session_id=None):
        print(f"\n--- SYNCING MONAI DATASETS (User: {current_user_session_id}) ---")
        try:
            base_url = url.rstrip('/')
            target_url = f"{base_url}{self.ENDPOINT_DATASTORE}"
            all_files = set() 

            try:
                params = {
                    'output': 'all',
                    'token': current_user_session_id,
                    'client_id': current_user_session_id
                }
                resp = requests.get(target_url, params=params, timeout=10, verify=False)
                
                if resp.status_code == 200:
                    full_data = resp.json()
                    if current_user_session_id:
                        self._filter_and_add(full_data, all_files, mode="private", user_id=current_user_session_id)
                else:
                    print(f"   -> Server Sync Error: Status {resp.status_code}")
            except Exception as e:
                print(f"   -> Connection Error: {e}")

            final_list = list(all_files)
            final_list.sort()
            print(f"--- SYNC COMPLETE: {len(final_list)} datasets visible. ---")
            return final_list
        except Exception as e:
            print(f"Critical Logic Error: {e}")
            return []

    def _filter_and_add(self, data, file_set, mode="public", user_id=None):
        try:
            objects_map = {} 
            if isinstance(data, dict):
                raw = data.get("objects", data)
                if isinstance(raw, dict): objects_map = raw
                elif isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            name = item.get('id') or item.get('image') or item.get('name')
                            if name: objects_map[name] = item
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        name = item.get('id') or item.get('image') or item.get('name')
                        if name: objects_map[name] = item
            
            for filename, details in objects_map.items():
                if not isinstance(filename, str) or "{" in filename: continue
                
                meta_client_id = details.get('client_id') 
                meta_uploaded_by = None
                
                raw_params = details.get('params') or details.get('info')
                if raw_params:
                    try:
                        p_dict = raw_params if isinstance(raw_params, dict) else json.loads(raw_params)
                        meta_uploaded_by = p_dict.get('uploaded_by') or p_dict.get('session_id')
                    except: pass

                if mode == "private" and user_id:
                    is_owner = False
                    if str(meta_client_id) == str(user_id): is_owner = True
                    elif str(meta_uploaded_by) == str(user_id): is_owner = True
                    
                    if not is_owner:
                        image_labels = details.get('labels')
                        if image_labels and isinstance(image_labels, dict) and str(user_id) in image_labels:
                            is_owner = True
                        elif str(details.get('tag')) == str(user_id):
                            is_owner = True
                    
                    if is_owner: file_set.add(filename)

        except Exception as e:
            print(f"   -> Filter Error: {e}")

    def process_upload(self, server_url, raw_image_name, is_public, image_node, label_node, is_new_patient, user_session_id, user_tag):
        print(f"\n--- UPLOAD STARTED ---")
        active_session_id = user_session_id
        final_image_id = raw_image_name 

        if is_new_patient:
            print("   -> Step 1: Uploading Source Image...")
            success_img, msg_img = self.upload_image(server_url, final_image_id, image_node, active_session_id, is_public=is_public)
            if not success_img: return False, f"Image Upload Failed: {msg_img}"
            time.sleep(1.0) 

        print("   -> Step 2: Uploading Segmentation...")
        success_lbl, msg_lbl = self.upload_label(server_url, final_image_id, user_tag, label_node, image_node, active_session_id, is_public)
        
        if not success_lbl: return False, f"Label Upload Failed: {msg_lbl}"
        return True, f"Successfully Uploaded: {final_image_id}"

    def upload_image(self, server_url, image_id, image_node, session_id, is_public=False):
        temp_path = None
        try:
            server_url = server_url.rstrip('/')
            api_url = f"{server_url}{self.ENDPOINT_IMAGE}"
            temp_filename = f"{image_id}.nii.gz"
            temp_path = os.path.join(slicer.app.temporaryPath, temp_filename)
            slicer.util.saveNode(image_node, temp_path)
            
            meta_info = {"uploaded_by": session_id, "ispublic": is_public}
            params = {'image': image_id, 'client_id': session_id, 'token': session_id, 'tag': session_id, 'params': json.dumps(meta_info)}
            
            with open(temp_path, 'rb') as f:
                resp = requests.put(api_url, params=params, files={'file': (temp_filename, f)}, timeout=120, verify=False)
            
            return resp.status_code in [200, 201], "OK" if resp.status_code in [200, 201] else f"Server Error: {resp.status_code}"
        except Exception as e: return False, str(e)
        finally:
            if temp_path and os.path.exists(temp_path): os.remove(temp_path)

    def upload_label(self, server_url, image_id, tag, label_node, ref_node, session_id, is_public_bool=False):
        temp_path = None
        temp_labelmap_node = None
        try:
            server_url = server_url.rstrip('/')
            api_url = f"{server_url}{self.ENDPOINT_LABEL}"
            temp_filename = f"label_{image_id}_{tag}.nii.gz"
            temp_path = os.path.join(slicer.app.temporaryPath, temp_filename)
            
            node_to_save = label_node
            extracted_label_info = []
            if label_node.IsA("vtkMRMLSegmentationNode"):
                segmentation = label_node.GetSegmentation()
                for i in range(segmentation.GetNumberOfSegments()):
                    seg_name = segmentation.GetSegment(segmentation.GetNthSegmentID(i)).GetName()
                    if "background" in seg_name.lower(): continue
                    extracted_label_info.append({"name": seg_name, "idx": i + 1})
                
                temp_labelmap_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
                if ref_node:
                    label_node.SetReferenceImageGeometryParameterFromVolumeNode(ref_node)
                    slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(label_node, temp_labelmap_node, slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY)
                else:
                    slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(label_node, temp_labelmap_node, slicer.vtkSegmentation.EXTENT_UNION_OF_SEGMENTS)
                node_to_save = temp_labelmap_node
            elif label_node.IsA("vtkMRMLLabelMapVolumeNode"):
                 extracted_label_info.append({"name": "LabelMap", "idx": 1})

            slicer.util.saveNode(node_to_save, temp_path)
            
            meta_data = {"session_id": session_id, "uploaded_by": session_id, "label_info": extracted_label_info, "is_public": is_public_bool}
            params = {'image': image_id, 'label': image_id, 'tag': tag, 'client_id': session_id, 'token': session_id}
            data_payload = {'params': json.dumps(meta_data)}
            
            with open(temp_path, 'rb') as f:
                resp = requests.put(api_url, params=params, data=data_payload, files={'label': (temp_filename, f)}, timeout=60, verify=False)
            
            return resp.status_code in [200, 201], "OK" if resp.status_code in [200, 201] else f"Server Error: {resp.status_code}"
        except Exception as e: return False, str(e)
        finally:
            if temp_labelmap_node: slicer.mrmlScene.RemoveNode(temp_labelmap_node)
            if temp_path and os.path.exists(temp_path): os.remove(temp_path)

    def download_image_and_label(self, server_url, image_id, user_tag, target_folder):
        import shutil
        try:
            print(f"\n--- DOWNLOAD STARTED -> {target_folder} ---")
            base_url = server_url.rstrip('/')
            active_token = user_tag

            image_url = f"{base_url}{self.ENDPOINT_IMAGE}"
            params = {'image': image_id, 'token': active_token, 'client_id': active_token}
            file_name = f"{image_id}.nii.gz"
            save_path = os.path.join(target_folder, file_name)
            
            resp = requests.get(image_url, params=params, stream=True, timeout=15, verify=False)
            if resp.status_code == 200:
                with open(save_path, 'wb') as f:
                    resp.raw.decode_content = True
                    shutil.copyfileobj(resp.raw, f)
                slicer.util.loadVolume(save_path)
            else: return False, f"Image Download Failed (Code: {resp.status_code})"

            label_url = f"{base_url}{self.ENDPOINT_LABEL}"
            label_params = {'label': image_id, 'tag': user_tag, 'token': user_tag, 'client_id': user_tag}
            label_name = f"label_{image_id}.nii.gz"
            label_save_path = os.path.join(target_folder, label_name)
            
            resp_lbl = requests.get(label_url, params=label_params, stream=True, timeout=10, verify=False)
            if resp_lbl.status_code == 200:
                with open(label_save_path, 'wb') as f:
                    resp_lbl.raw.decode_content = True
                    shutil.copyfileobj(resp_lbl.raw, f)
                slicer.util.loadLabelVolume(label_save_path)
            
            return True, "Download Success"
        except Exception as e: return False, f"Error: {e}"

    def delete_resource(self, server_url, image_id, user_session_id, delete_mode="label"):
        try:
            server_url = server_url.rstrip('/')
            active_token = user_session_id 
            endpoint = self.ENDPOINT_IMAGE if delete_mode == "image" else self.ENDPOINT_LABEL
            api_url = f"{server_url}{endpoint}"
            params = {'id': image_id, 'token': active_token, 'client_id': active_token}
            if delete_mode == "label": params['tag'] = user_session_id 

            resp = requests.delete(api_url, params=params, timeout=10, verify=False)
            
            if resp.status_code in [200, 204]: return True, f"{delete_mode.upper()} Deleted Successfully."
            elif resp.status_code in [401, 403]: return False, "Access Denied."
            else: return False, f"Server Error: {resp.status_code}"
        except Exception as e: return False, f"Exception: {e}"
