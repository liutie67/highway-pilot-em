# Highway Pilot - ElectroMechanical 🛣️⚡

> **[中文]** 高速公路机电工程自动化设计辅助工具
>
> **[English]** Automated Design Toolkit for Highway Electromechanical Engineering
>
> **[Français]** Copilote de conception automatisée pour l'ingénierie électromécanique autoroutière

---

## 📖 简介 (Introduction)

**HighwayPilot-EM** 是一个专为线性基础设施（如高速公路、隧道、地铁）设计的 Python 自动化 CAD 工具。

在传统的机电设计中，工程师需要手动在几十公里的线路上一个个放置摄像机、情报板等设备，并手动计算线缆长度、统计数量、绘制供电和传输系统图。这个过程繁琐且容易出错。

本项目旨在通过读取**道路中心线 (Centerline)** 和**设计规则**，全自动完成“布点 -> 统计 -> 系统图绘制”的工作流，极大提高出图效率。

<details>
<summary><strong>Read in English</strong></summary>

**HighwayPilot-EM** is a Python-based automation tool designed for linear infrastructure projects (highways, tunnels, subways).

It automates the tedious process of manually placing devices along kilometers of alignments, calculating cable lengths, and drawing system diagrams. By parsing the **Route Centerline** and **Design Rules**, this tool automates the workflow from "Layout -> Statistics -> System Diagram Generation", significantly improving efficiency.
</details>

<details>
<summary><strong>Lire en Français</strong></summary>

**HighwayPilot-EM** est un outil d'automatisation basé sur Python conçu pour les projets d'infrastructures linéaires (autoroutes, tunnels, métros).

Il automatise le processus fastidieux de placement manuel des équipements sur des kilomètres de tracés, le calcul des longueurs de câbles et le dessin des schémas système. En analysant l'**axe routier (Centerline)** et les **règles de conception**, cet outil automatise le flux de travail "Implantation -> Statistiques -> Génération de schémas", améliorant considérablement l'efficacité de la production de plans.
</details>

---

## 🚀 核心功能 (Key Features)

### 1. 沿线设备自动布设
**Automated Device Layout / Implantation Automatisée**

* 基于 DXF 格式的道路中心线（Polyline），自动计算桩号（Stationing）。
* 支持按规则（如每 2km 一处监控、每 150m 一处车检器）自动在模型空间批量生成设备图块。
* 自动处理弯道角度，确保设备图标与道路走向垂直或平行。

<details>
<summary><em>English & Français Translations</em></summary>

* **[EN]** Automatically places device blocks along the alignment based on spacing rules (e.g., CCTV every 2km). Handles curve rotation to ensure blocks align with the road tangent.
* **[FR]** Place automatiquement les blocs d'équipements le long du tracé en fonction des règles d'espacement (ex: caméra tous les 2 km). Gère la rotation dans les courbes pour assurer l'alignement des blocs avec la tangente de la route.
</details>

### 2. 智能报表生成
**Smart Data Export / Exportation Intelligente de Données**

* **点位一览表**: 自动导出包含设备名称、桩号、坐标(X,Y)、所属路段的 Excel 表格。
* **工程量统计**: 自动汇总各类设备数量，生成 BOM (Bill of Materials)。

<details>
<summary><em>English & Français Translations</em></summary>

* **[EN]** Automatically exports Device Location Tables (Station number, Coordinates) and generates Bill of Materials (BOM) into Excel files.
* **[FR]** Exporte automatiquement les tableaux de localisation des équipements (PK, Coordonnées) et génère la nomenclature (BOM) dans des fichiers Excel.
</details>

### 3. 系统图自动绘制
**Automatic System Diagrams / Schémas Système Automatiques**

* **供电系统图 (Power Distribution)**: 根据点位分布和电压降公式，自动绘制箱变供电回路图，计算线缆规格和压降。
* **网络传输图 (Network Topology)**: 根据设备位置自动生成光缆传输拓扑图，计算光芯分配。

<details>
<summary><em>English & Français Translations</em></summary>

* **[EN]** Generates Power Supply Diagrams (calculating voltage drop and cable sizing) and Network Transmission Topology Diagrams based on spatial distribution.
* **[FR]** Génère des schémas d'alimentation électrique (calcul de la chute de tension et dimensionnement des câbles) et des topologies de transmission réseau basés sur la distribution spatiale.
</details>

---

## 🛠️ 技术栈 (Tech Stack)

| Component | Library / Tool | Description (CN/EN/FR) |
| :--- | :--- | :--- |
| **Language** | `Python 3.12+` | 核心语言 / Core Language / Langage principal |
| **CAD Core** | `ezdxf` | 读写 .dxf 文件 / Reading & Writing DXF / Lecture et écriture DXF |
| **Data** | `pandas`, `openpyxl`| Excel 自动化处理 / Excel Automation / Automatisation Excel |
| **Math** | `numpy` | 矢量计算 / Vector Math / Calcul vectoriel |

---

## 📦 安装与使用 (Installation & Usage)

### 前置要求 (Prerequisites / Prérequis)

```bash
pip install ezdxf pandas openpyxl numpy
