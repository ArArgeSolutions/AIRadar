# AIRadar

AIRadar is a 3D Slicer extension that connects to a clinical backend and MONAI Label server to browse, download, visualize and upload patient volumes and segmentations, with optional streaming to HoloLens via Slicer Virtual Reality. Known related patents: none.

![AIRadar Screenshot](Resources/Screenshots/AIRadar_Screenshot1.png)

## Modules

- **AIRadar**  
  Provides device pairing with a clinical web portal, patient list browsing and download from the backend, MONAI Label dataset management (upload/download/delete), and optional streaming of the current 3D scene to HoloLens using Slicer Virtual Reality.

## Usage

1. Open the **AIRadar** module in 3D Slicer.
2. Pair your device using the 4-digit code on the clinical web portal.
3. After successful authentication, browse the patient list and load cases into Slicer.
4. Optionally manage MONAI Label datasets (upload labels, download cases).
5. Use the HoloLens panel to connect to a headset and stream the current 3D scene.

## Publication

No dedicated publication is currently available for AIRadar.  
(If a paper becomes available in the future, add the link or PubMed reference here.)

## Privacy and Safety

AIRadar does not download or execute any third-party binaries from untrusted sources.  
All communication with the clinical backend and MONAI Label server happens over HTTPS and is only triggered by explicit user actions (e.g., logging in, downloading a patient case, uploading a segmentation).  
No data is sent anywhere without user consent.


## License

This extension is released under the **MIT License**. See [LICENSE](LICENSE) for details.

