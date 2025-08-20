from ansys.fluent.core import launch_fluent
import time
from pathlib import Path

# Ruta base = carpeta donde está este script
base_dir = Path(__file__).resolve().parent

# Archivos relativos al proyecto
case = base_dir / "WorkBench_files" / "dp0" / "FFF" / "Fluent" / "FFF-Setup-Output.cas.h5"
setf = base_dir / "WorkBench_files" / "dp0" / "FFF" / "Fluent" / "FFF.set"
data = case.with_suffix(".dat.h5")  # si existe, lo ignoraremos (setup cambia)

solver = launch_fluent(
    mode="solver",
    precision="double",
    processor_count=4,
    ui_mode="gui",
    product_version="25.1.0",
)

# 1) Abrir el case
solver.tui.file.read_case(str(case))

# 2) (Opcional) aplicar settings si existe .set
if setf.exists():
    solver.tui.file.read_settings(str(setf))
    print(f"Settings aplicados desde: {setf}")

# 3) Forzar modelos requeridos
#    Intentamos primero con la API de Settings; si no funciona, usamos TUI.
# --- Forzar modelos: Energy ON, Laminar, Multiphase = VOF (implícito, 2 fases)
# 1) NO aplicar el .set si quieres VOF (lo desactivamos de momento)
# if setf.exists():
#     solver.tui.file.read_settings(str(setf))
#     print(f"Settings aplicados desde: {setf}")

# 2) Forzar modelos con la Settings API (preferida)
# 1) NO aplicar el .set si quieres VOF (lo desactivamos de momento)
# if setf.exists():
#     solver.tui.file.read_settings(str(setf))
#     print(f"Settings aplicados desde: {setf}")

# 2) Forzar modelos con la Settings/Setup API (preferida) y fallback TUI
def force_vof_only():
    """
    Fuerza Models > Multiphase = Volume of Fluid (VOF),
    intenta fijar formulación 'implicit' y 2 fases.
    Verifica al final y reporta el estado.
    """
    vof_ok = False

    # --- 1) setup API directa (si existe en tu build) ---
    try:
        mp = solver.setup.models.multiphase
        # activar VOF
        mp.vof_model = True
        # opcionales (si existen en tu build):
        try: mp.formulation = "implicit"
        except: pass
        for attr in ("number_of_phases", "no_of_phases", "phases_count"):
            try:
                setattr(mp, attr, 2)
                break
            except:
                pass
        vof_ok = True
        print("✓ Multiphase=VOF (setup API)")
    except Exception as e_setup:
        # --- 2) settings API alternativa ---
        try:
            ms = solver.settings.setup.models
            ms.multiphase.model = "vof"
            # intenta fijar implícito y 2 fases en ramas posibles
            try:
                ms.multiphase.vof.formulation = "implicit"
            except Exception:
                try:
                    ms.multiphase.formulation = "implicit"
                except Exception:
                    pass
            for holder in (getattr(ms, "multiphase", None), getattr(ms.multiphase, "vof", None)):
                if holder is None:
                    continue
                for attr in ("number_of_phases", "no_of_phases", "phases_count"):
                    try:
                        setattr(holder, attr, 2)
                        break
                    except:
                        pass
            vof_ok = True
            print("✓ Multiphase=VOF (settings API)")
        except Exception as e_settings:
            # --- 3) TUI (varias firmas típicas) ---
            tried = [
                ("vof",),                          # /define/models/multiphase vof
                ("vof", "implicit"),               # + implicit
                ("vof", "implicit", "no"),         # + no open-channel
                ("vof", "implicit", "no", "2"),    # + 2 phases
            ]
            for args in tried:
                try:
                    solver.tui.define.models.multiphase(*args)
                    vof_ok = True
                    print(f"✓ Multiphase=VOF (TUI args={args})")
                    break
                except Exception:
                    continue

    # --- 4) verificación y pequeño informe ---
    status = "desconocido"
    if vof_ok:
        # intenta leer el estado vía settings
        try:
            m = solver.settings.setup.models.multiphase
            # algunas builds tienen .model, otras un booleano vof_model
            model_val = getattr(m, "model", None)
            vof_flag = getattr(getattr(solver.setup.models, "multiphase", object), "vof_model", None)
            if model_val == "vof" or vof_flag is True:
                status = "VOF"
        except Exception:
            pass

    if status != "VOF":
        print("⚠️ VOF podría no haber quedado activo aún. Revisa en GUI: "
              "Define → Models → Multiphase → selecciona 'Volume of Fluid', "
              "Formulation=Implicit, Eulerian Phases=2.")
    else:
        # (opcional) asignar materiales por defecto a las fases si el árbol existe
        try:
            phases = None
            try:
                phases = solver.setup.models.multiphase.phases
            except Exception:
                phases = solver.settings.setup.models.multiphase.phases
            if phases and ("primary" in phases) and ("secondary" in phases):
                if getattr(phases["primary"], "material", None) is not None:
                    phases["primary"].material = "air"
                if getattr(phases["secondary"], "material", None) is not None:
                    phases["secondary"].material = "water-liquid"
                print("✓ Fases: primary=air, secondary=water-liquid")
        except Exception:
            pass
        print("✅ Verificado: Multiphase = VOF")

force_vof_only()


# 4) (Importante) No cargar .dat.h5 si cambiamos el setup
if data.exists():
    print(f"⚠️ Se encontró {data.name}, pero NO se cargará porque acabamos de cambiar modelos "
          f"(VOF/Laminar/Energy). Cargar datos con setup distinto suele fallar o ser inconsistente.")

# 5) Mostrar malla
try:
    solver.tui.display.mesh()
except Exception:
    pass

print("✅ Case cargado, setup forzado (VOF + Energy ON + Laminar) y malla mostrada. Deja esta consola abierta.")

# 6) Mantener vivo mientras Fluent esté abierto
try:
    while True:
        try:
            solver.health_check.check_health()
        except Exception:
            print("🔻 Fluent se ha cerrado. Finalizando script.")
            break
        time.sleep(2)
except KeyboardInterrupt:
    print("⏹ Interrumpido por el usuario. Cerrando script.")
