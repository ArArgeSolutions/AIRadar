import os
import requests
import time
import qt
import slicer
import json
import uuid
import random
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
        Professional client for MONAI Label server integration. 
        Supports secure image/label upload, download, and management.
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
        # Generate Random Device Code and Session ID
        self.device_code = str(random.randint(1000, 9999))
        self.session_id = str(uuid.uuid4())[:8] 
        self.timer = qt.QTimer()
        self.is_logged_in = False
        self.current_sis_id = None 

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = AIRadarLogic()

        self.authPanel = slicer.qMRMLCollapsibleButton()
        self.authPanel.text = "1. DEVICE PAIRING & AUTHENTICATION"
        self.layout.addWidget(self.authPanel)
        authLayout = qt.QFormLayout(self.authPanel)

        self.apiLine = qt.QLineEdit("https://airadar.uzem.afsu.edu.tr/")
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

        self.appPanel = slicer.qMRMLCollapsibleButton()
        self.appPanel.text = "2. DATASET MANAGEMENT"
        self.appPanel.enabled = False
        self.layout.addWidget(self.appPanel)
        appLayout = qt.QFormLayout(self.appPanel)

        self.userLabel = qt.QLabel("Active User: -")
        self.userLabel.setStyleSheet("font-weight: bold; color: #666;")
        appLayout.addRow(self.userLabel)

        self.serverImagesCombo = qt.QComboBox()
        self.serverImagesCombo.setToolTip("Available datasets on the server.")
        appLayout.addRow("Server Datasets:", self.serverImagesCombo)
        
        self.refreshBtn = qt.QPushButton("Refresh Dataset List")
        appLayout.addRow(self.refreshBtn)
        
        self.downloadBtn = qt.QPushButton("DOWNLOAD SELECTED CASE")
        self.downloadBtn.setToolTip("Downloads the selected Image and Segmentation (if available).")
        self.downloadBtn.setStyleSheet("background-color: #007bff; color: white; font-weight: bold; padding: 6px;")
        appLayout.addRow(self.downloadBtn)
        
        self.deleteBtn = qt.QPushButton("Delete Resource")
        self.deleteBtn.setToolTip("Remove datasets or labels from the server.")
        self.deleteBtn.setStyleSheet("color: #d9534f; font-weight: bold;")
        appLayout.addRow(self.deleteBtn)

        self.uploadPanel = slicer.qMRMLCollapsibleButton()
        self.uploadPanel.text = "3. UPLOAD NEW CASE"
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
        self.publicModeCheckBox.setToolTip("If checked, the dataset will be visible to all users (Read-Only access for others).")
        uploadLayout.addRow(self.publicModeCheckBox)

        self.isNewPatientCheckBox = qt.QCheckBox("New Case Label Image Upload")
        self.isNewPatientCheckBox.setToolTip("Check this if the Source Image does not exist on the server yet.")
        uploadLayout.addRow(self.isNewPatientCheckBox)

        self.uploadBtn = qt.QPushButton("UPLOAD TO SERVER")
        self.uploadBtn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; height: 40px;")
        uploadLayout.addRow(self.uploadBtn)

        self.layout.addStretch(1)

        self.registerDevice()
        self.timer.timeout.connect(self.checkLoginStatus)
        self.timer.start(2000)

        self.refreshBtn.connect('clicked(bool)', self.onRefreshList)
        self.uploadBtn.connect('clicked(bool)', self.onUpload)
        self.deleteBtn.connect('clicked(bool)', self.onDelete)
        self.downloadBtn.connect('clicked(bool)', self.onDownload)
        self.serverImagesCombo.currentTextChanged.connect(self.onImageSelected)
        self.publicModeCheckBox.connect('toggled(bool)', self.onPublicToggled)

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
        
        self.userLabel.setText(f"Operator: {name} | ID: {sis_id}")
        self.userLabel.setStyleSheet("color: green; font-weight: bold;")
        self.onRefreshList()

    def onPublicToggled(self, checked):
        if checked: self.publicModeCheckBox.setStyleSheet("color: #d9534f; font-weight: bold;")
        else: self.publicModeCheckBox.setStyleSheet("")

    def onRefreshList(self):
        if not self.session_id: 
            self.statusLabel.setText("Please login first.")
            return

        self.serverImagesCombo.clear()
        self.statusLabel.setText("Syncing...")
        slicer.app.processEvents() 
        
        images = self.logic.fetch_all_images(self.monaiLine.text, current_user_session_id=self.session_id)
        
        if images: 
            self.serverImagesCombo.addItems(images)
            self.statusLabel.setText(f"{len(images)} datasets found.")
        else:
            self.statusLabel.setText("No datasets found.")

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
        
        selected_folder = qt.QFileDialog.getExistingDirectory(
            self.parent, 
            "Select Download Destination"
        )
        
        if not selected_folder:
            return 

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
            qt.QMessageBox.information(slicer.util.mainWindow(), "Download Complete", 
                                     f"Dataset saved and loaded successfully:\n{selected_folder}")
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
            # Private ve Image siliyorsa bir kere soralım
            confirm = qt.QMessageBox.question(slicer.util.mainWindow(), "Confirm Delete", 
                                              "Delete this case permanently?", 
                                              qt.QMessageBox.Yes | qt.QMessageBox.No)
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
            qt.QMessageBox.information(slicer.util.mainWindow(), "Success", "Resource deleted successfully.")
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

    def fetch_all_images(self, url, current_user_session_id=None):
        """
        Retrieves datasets and applies STRICT ownership filtering using the logic from the old stable code.
        """
        print(f"\n--- SYNCING DATASETS (User: {current_user_session_id}) ---")
        try:
            base_url = url.rstrip('/')
            target_url = f"{base_url}/datastore/" 
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
            print(f"--- SYNC COMPLETE: {len(final_list)} datasets visible to user. ---")
            return final_list

        except Exception as e:
            print(f"Critical Logic Error: {e}")
            return []

    def _filter_and_add(self, data, file_set, mode="public", user_id=None):
        """
        GÜNCELLENMİŞ FİLTRELEME MANTIĞI:
        Artık görüntünün 'labels' listesini kontrol ederek, kullanıcının session_id'si ile
        oluşturulmuş bir label var mı diye bakar.
        """
        try:
            objects_map = {} 
            
            if isinstance(data, dict):
                raw = data.get("objects", data)
                if isinstance(raw, dict):
                    objects_map = raw
                elif isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, str): objects_map[item] = {}
                        elif isinstance(item, dict):
                            name = item.get('id') or item.get('image') or item.get('name')
                            if name: objects_map[name] = item
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, str): objects_map[item] = {}
                    elif isinstance(item, dict):
                        name = item.get('id') or item.get('image') or item.get('name')
                        if name: objects_map[name] = item
            
            count = 0
            for filename, details in objects_map.items():
                if not isinstance(filename, str) or "{" in filename: continue
                
                meta_client_id = details.get('client_id') 
                
                meta_uploaded_by = None
                meta_is_public = None
                
                raw_params = details.get('params') or details.get('info')
                if raw_params:
                    try:
                        p_dict = raw_params if isinstance(raw_params, dict) else json.loads(raw_params)
                        meta_uploaded_by = p_dict.get('uploaded_by') or p_dict.get('session_id')
                        meta_is_public = p_dict.get('ispublic') or p_dict.get('is_public')
                    except:
                        pass

                if mode == "public":
                    is_public_by_name = filename.startswith("public_") or "public" in filename
                    is_public_by_meta = (meta_is_public is True) or (str(meta_is_public).lower() == 'true')
                    
                    if is_public_by_name or is_public_by_meta:
                        file_set.add(filename)
                        count += 1

                elif mode == "private" and user_id:
                    is_owner = False
                    
                    if str(meta_client_id) == str(user_id):
                        is_owner = True
                    elif str(meta_uploaded_by) == str(user_id):
                        is_owner = True
                    
                    if not is_owner:
                        image_labels = details.get('labels')
                        
                        if image_labels and isinstance(image_labels, dict):
                            if str(user_id) in image_labels:
                                is_owner = True
                        
                        elif str(details.get('tag')) == str(user_id):
                            is_owner = True
                    
                    if is_owner:
                        file_set.add(filename)
                        count += 1
                        

        except Exception as e:
            print(f"   -> Filter Error: {e}")

    def process_upload(self, server_url, raw_image_name, is_public, image_node, label_node, is_new_patient, user_session_id, user_tag):
        """
        Upload Logic: New Code Structure but ensures Metadata is written correctly.
        """
        print(f"\n--- UPLOAD STARTED ---")
        
        active_session_id = user_session_id
        tag_to_use = user_tag
        final_image_id = raw_image_name 
        
        print(f"   -> Mode: User Upload (Tag: {tag_to_use})")
        print(f"   -> Target ID: {final_image_id}")

        if is_new_patient:
            print("   -> Step 1: Uploading Source Image...")
            success_img, msg_img = self.upload_image(server_url, final_image_id, image_node, active_session_id, is_public=is_public)
            if not success_img:
                return False, f"Image Upload Failed: {msg_img}"
            time.sleep(1.0) 
        else:
            print("   -> Step 1: Image upload skipped (Label only).")

        print("   -> Step 2: Uploading Segmentation...")
        success_lbl, msg_lbl = self.upload_label(
            server_url=server_url,
            image_id=final_image_id,
            tag=tag_to_use,
            label_node=label_node,
            ref_node=image_node,
            session_id=active_session_id,
            is_public_bool=is_public
        )
        
        if not success_lbl:
             if "500" in str(msg_lbl):
                 return False, "Server Error (500): Image likely missing on server."
             return False, f"Label Upload Failed: {msg_lbl}"
        
        return True, f"Successfully Uploaded: {final_image_id}"

    def upload_image(self, server_url, image_id, image_node, session_id, is_public=False):
        """
        CRITICAL UPDATE: Writes metadata into 'params' so filtering works later.
        """
        temp_path = None
        try:
            server_url = server_url.rstrip('/')
            api_url = f"{server_url}/datastore/image"
            
            temp_filename = f"{image_id}.nii.gz"
            temp_path = os.path.join(slicer.app.temporaryPath, temp_filename)
            slicer.util.saveNode(image_node, temp_path)
            
            meta_info = {
                "uploaded_by": session_id,
                "ispublic": is_public
            }

            params = {
                'image': image_id, 
                'client_id': session_id,
                'token': session_id,
                'params': json.dumps(meta_info) 
            }
            
            with open(temp_path, 'rb') as f:
                resp = requests.put(api_url, params=params, files={'file': (temp_filename, f)}, timeout=120, verify=False)
            
            if resp.status_code in [200, 201]:
                return True, "OK"
            else:
                return False, f"Server Error: {resp.status_code}"
        except Exception as e:
            return False, str(e)
        finally:
            if temp_path and os.path.exists(temp_path): os.remove(temp_path)

    def upload_label(self, server_url, image_id, tag, label_node, ref_node, session_id, is_public_bool=False):
        temp_path = None
        temp_labelmap_node = None
        try:
            server_url = server_url.rstrip('/')
            api_url = f"{server_url}/datastore/label"
            
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
                    slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(
                        label_node, temp_labelmap_node, slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY)
                else:
                    slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(
                        label_node, temp_labelmap_node, slicer.vtkSegmentation.EXTENT_UNION_OF_SEGMENTS)
                node_to_save = temp_labelmap_node
            elif label_node.IsA("vtkMRMLLabelMapVolumeNode"):
                 extracted_label_info.append({"name": "LabelMap", "idx": 1})

            slicer.util.saveNode(node_to_save, temp_path)
            
            meta_data = {
                "session_id": session_id, 
                "uploaded_by": session_id, 
                "label_info": extracted_label_info,
                "is_public": is_public_bool
            }
            
            params = {
                'image': image_id, 
                'label': image_id, 
                'tag': tag, 
                'client_id': session_id, 
                'token': session_id 
            }
            data_payload = {'params': json.dumps(meta_data)}
            
            with open(temp_path, 'rb') as f:
                resp = requests.put(api_url, params=params, data=data_payload, files={'label': (temp_filename, f)}, timeout=60, verify=False)
            
            if resp.status_code in [200, 201]:
                return True, "OK"
            else:
                return False, f"Server Error: {resp.status_code}"
        except Exception as e:
            return False, str(e)
        finally:
            if temp_labelmap_node: slicer.mrmlScene.RemoveNode(temp_labelmap_node)
            if temp_path and os.path.exists(temp_path): os.remove(temp_path)

    def download_image_and_label(self, server_url, image_id, user_tag, target_folder):
        import shutil
        try:
            print(f"\n--- DOWNLOAD STARTED -> {target_folder} ---")
            base_url = server_url.rstrip('/')
            
            # Logic: Try user token first. 
            active_token = user_tag

            # 1. Download Source Image
            image_url = f"{base_url}/datastore/image"
            params = {'image': image_id, 'token': active_token, 'client_id': active_token}
            file_name = f"{image_id}.nii.gz"
            save_path = os.path.join(target_folder, file_name)
            
            resp = requests.get(image_url, params=params, stream=True, timeout=15, verify=False)
            
            if resp.status_code == 200:
                with open(save_path, 'wb') as f:
                    resp.raw.decode_content = True
                    shutil.copyfileobj(resp.raw, f)
                
                loaded_node = slicer.util.loadVolume(save_path)
                if loaded_node: loaded_node.SetName(image_id)
            else:
                return False, f"Image Download Failed (Code: {resp.status_code})"

            label_url = f"{base_url}/datastore/label"
            label_params = {'label': image_id, 'tag': user_tag, 'token': user_tag, 'client_id': user_tag}
            label_name = f"label_{image_id}.nii.gz"
            label_save_path = os.path.join(target_folder, label_name)
            
            resp_lbl = requests.get(label_url, params=label_params, stream=True, timeout=10, verify=False)
            
            if resp_lbl.status_code == 200:
                with open(label_save_path, 'wb') as f:
                    resp_lbl.raw.decode_content = True
                    shutil.copyfileobj(resp_lbl.raw, f)
                
                loaded_lbl = slicer.util.loadLabelVolume(label_save_path)
                if loaded_lbl: loaded_lbl.SetName(f"Label_{image_id}")
            else:
                print("   -> No segmentation found (Label download skipped).")
            
            return True, "Download Success"
        except Exception as e:
            return False, f"Error: {e}"

    def delete_resource(self, server_url, image_id, user_session_id, delete_mode="label"):
        """
        REVISED DELETE: Always uses the User's Token.
        """
        try:
            server_url = server_url.rstrip('/')
            print(f"\n--- DELETE REQUEST: {image_id} ({delete_mode}) ---")
            
            active_token = user_session_id 

            endpoint = "/datastore/image" if delete_mode == "image" else "/datastore/label"
            api_url = f"{server_url}{endpoint}"
            
            params = {
                'id': image_id, 
                'token': active_token, 
                'client_id': active_token
            }
            
            if delete_mode == "label": 
                params['tag'] = user_session_id 

            resp = requests.delete(api_url, params=params, timeout=10, verify=False)
            
            if resp.status_code in [200, 204]:
                return True, f"{delete_mode.upper()} Deleted Successfully."
            elif resp.status_code == 403 or resp.status_code == 401:
                return False, "Access Denied: You do not own this resource."
            else:
                return False, f"Server Error: {resp.status_code}"

        except Exception as e:
            return False, f"Exception: {e}"