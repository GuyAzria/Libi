<div align="center">
  <img src="image/icon2.png" alt="LIBI Logo" width="115" />
</div>

# **LIBI (Ladder Interface & Building Intelligence)**

> [!CAUTION]
> **⚠️ IMPORTANT NOTE: BETA SOFTWARE**
> 
> LIBI is currently in BETA. It is not recommended to install this on a production system unless you are deeply curious, willing to experiment, and want to help test and improve the project.

![LIBI Interface](image/LIBI2.png)
![LIBI Interface](image/LIBI1.png)

## **Not a Node-RED Replacement**

**Please note:** LIBI is *not* intended to replace Node-RED. It is simply an alternative approach to writing automations in Home Assistant. It is specifically designed for electricians, PLC (Programmable Logic Controller) programmers, or anyone who prefers a straightforward, graphical way to learn and write logic.

## **What is LIBI?**

LIBI is a graphical editor that takes your existing Home Assistant automations and automatically translates them into a LADDER logic representation. It allows you to:

* Add and modify automation logic using a visual interface.  
* Save the resulting logic directly back to standard Home Assistant YAML files.  
* Execute the automations natively within Home Assistant, just like any standard automation.

### **IEC 61131-3 Compliance**

The software is built upon the **IEC 61131-3** standard, the international standard defining programming languages for PLCs. Specifically, LIBI utilizes:

* **LD (Ladder Diagram):** The classic ladder logic format, adapted with minor deviations to ensure seamless compatibility with Home Assistant's native entities and execution models.

## **Key Features**

* **Integrated Helper Management:** Search for, manage, and insert variables (Helpers) directly from within the graphical editor.  
* **Project and File Grouping:** Save and manage groups of YAML files collectively. In LIBI, every **NET** functions as an individual YAML file. This allows you to open a single project and view all related ladders (e.g., "Garden Automations", "Security Automations") in one unified workspace.

## **Installation**

**Requirements:** Home Assistant 2025.1 or newer, and an administrator account. LIBI edits your automations, so like Home Assistant's own automation editor it is available to administrators only.

### With HACS

1. In HACS, open the menu (⋮) and choose **Custom repositories**.
2. Add `https://github.com/GuyAzria/Libi` with the type **Integration**.
3. Search for **LIBI**, download it, and restart Home Assistant.
4. Go to **Settings ▸ Devices & services ▸ Add integration** and add **LIBI**.

LIBI then appears in the sidebar.

### Manually

Download `libi.zip` from the [latest release](https://github.com/GuyAzria/Libi/releases/latest), unpack it into `config/custom_components/libi/`, restart Home Assistant, and add the integration as in step 4.

## **What LIBI changes in your configuration**

* LIBI reads and writes the same `automations.yaml`, `scripts.yaml` and `scenes.yaml` that Home Assistant's own editors use, and reloads them after a save. Nothing has to be added to `configuration.yaml`.
* Entries you wrote yourself, by hand or in the Home Assistant editor, are kept exactly as they are. A file is only written when its content actually changes.
* If one of those files cannot be read (for example because it contains a syntax error), LIBI saves nothing and tells you why.
* Projects are stored as `.libi` files in `config/libi/`, so they are part of your Home Assistant backup.

## **🚀 Future Roadmap**

* **AI-Powered Logic Generation:** One of our upcoming milestones is integrating AI capabilities. Users will be able to generate LADDER logic simply by writing a natural language query and selecting the relevant variables.

<p align="center">Made with ❤️ for the Home Assistant community by Guy Azria</p>