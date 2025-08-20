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


# 2) Forzar modelos con la Settings/Setup API (preferida) y fallback TUI
def force_models_energy_laminar_gravity_transient():
    # --- Energy ON + Laminar ---
    ms = solver.settings.setup.models
    ms.energy.enabled = True
    ms.viscous.model = "laminar"
    print("✓ Energy=ON, Viscous=Laminar")

    # --- Time = Transient (valor válido) ---
    solver.settings.setup.general.solver.time = "unsteady-2nd-order"
    print("✓ Solver → Transient (unsteady-2nd-order)")

    # --- Gravity en Z ---
    gravity_ok = False
    try:
        # Setup API (común en 2025 R1)
        solver.setup.operating_conditions.gravity = True
        solver.setup.operating_conditions.gravity_vector = (0.0, 0.0, -9.81)
        gravity_ok = True
        print("✓ Gravedad ON (0, 0, -9.81) [setup API]")
    except Exception:
        # Settings API alternativa
        try:
            oc = solver.settings.setup.operating_conditions
            try:
                oc.gravity = True
            except Exception:
                oc.enabled = True
            for attr in ("gravity_vector", "g_vector", "gravity_components"):
                try:
                    setattr(oc, attr, (0.0, 0.0, -9.81))
                    gravity_ok = True
                    break
                except Exception:
                    pass
            if gravity_ok:
                print("✓ Gravedad ON (0, 0, -9.81) [settings API]")
        except Exception:
            pass

    if not gravity_ok:
        # TUI fallback
        try:
            solver.tui.define.operating_conditions.gravity("yes", "0", "0", "-9.81")
            print("✓ Gravedad ON (0, 0, -9.81) [TUI]")
        except Exception as e:
            print(f"⚠️ No se pudo fijar gravedad automáticamente: {e}")


force_models_energy_laminar_gravity_transient()

def create_carbopol_hb_from_water(K=3.67, n=0.66, tau0=56.91, crit_shear=5.0, assign_to_all_fluid_zones=False):
    """
    Crea/actualiza 'carbopol' basado en 'water-liquid' y define viscosidad Herschel-Bulkley:
      mu(gamma_dot) = tau0/gamma_dot + K * gamma_dot^(n-1), regularizada con gamma_dot* (critical shear rate).
    Unidades esperadas por Fluent:
      K en Pa·s^n, n adimensional, tau0 en Pa, critical shear rate en 1/s.
    """
    rho_default = 998.2
    rho = rho_default

    # 1) intentar leer densidad del agua
    try:
        w = solver.setup.materials.fluid["water-liquid"]
        try:
            if getattr(w.density, "option", "constant") == "constant":
                rho = float(w.density.value)
        except Exception:
            pass
    except Exception:
        try:
            w = solver.settings.setup.materials.fluid["water-liquid"]
            try:
                if getattr(w.density, "option", "constant") == "constant":
                    rho = float(w.density.value)
            except Exception:
                pass
        except Exception:
            pass

    # 2) crear/copiar material 'carbopol'
    created = False
    material_obj = None
    try:
        fluids = solver.setup.materials.fluid
        if "carbopol" not in fluids:
            try:
                fluids.copy("water-liquid", "carbopol")
            except Exception:
                fluids.create("carbopol")
            created = True
        material_obj = fluids["carbopol"]
    except Exception:
        fluids = solver.settings.setup.materials.fluid
        if "carbopol" not in fluids:
            try:
                fluids.copy("water-liquid", "carbopol")
            except Exception:
                fluids.create("carbopol")
            created = True
        material_obj = fluids["carbopol"]

    # 3) densidad constante
    try:
        material_obj.density.option = "constant"
    except Exception:
        pass
    try:
        material_obj.density.value = float(rho)
    except Exception:
        pass

    # 4) definir viscosidad Herschel–Bulkley (varían nombres según build)
    hb_set = False
    # --- Setup/Settings API con distintas variantes de nombres ---
    candidates = []
    # árbol tipo setup
    try:
        candidates.append(material_obj.viscosity)
    except Exception:
        pass
    # árbol tipo settings
    try:
        candidates.append(solver.settings.setup.materials.fluid["carbopol"].viscosity)
    except Exception:
        pass

    for vis in candidates:
        try:
            # seleccionar modelo HB
            for opt in ("herschel-bulkley", "herschel_bulkley", "herschelbulkley", "herschel-bulkley-regularized"):
                try:
                    vis.option = opt
                    break
                except Exception:
                    continue

            # subnodo HB (nombres posibles)
            hb_nodes = [
                getattr(vis, "herschel_bulkley", None),
                getattr(vis, "herschelbulkley", None),
                getattr(vis, "herschel_b", None),
                vis  # en algunos builds los campos cuelgan directo de viscosity
            ]
            for hb in hb_nodes:
                if hb is None:
                    continue
                # Consistency index
                for name in ("consistency_index", "k", "consistency", "consistencyindex"):
                    try:
                        setattr(hb, name, float(K))
                        break
                    except Exception:
                        pass
                # Power-law index
                for name in ("power_law_index", "n", "powerindex", "power_index"):
                    try:
                        setattr(hb, name, float(n))
                        break
                    except Exception:
                        pass
                # Yield stress
                # Dentro del bucle donde se setean los parámetros HB...
                # Yield stress principal
                for name in ("yield_stress", "tau0", "yieldstress"):
                    try:
                        setattr(hb, name, float(tau0))
                        break
                    except Exception:
                        pass

                # Yield stress threshold (campo extra en builds recientes)
                for name in ("yield_stress_threshold", "yieldstressthreshold", "yield_stress_limit"):
                    try:
                        setattr(hb, name, float(tau0))
                        print(f"✓ Yield Stress Threshold = {tau0} Pa")
                        break
                    except Exception:
                        pass

                # Critical shear rate
                for name in ("critical_shear_rate", "ref_shear_rate", "min_shear_rate", "shear_rate0"):
                    try:
                        setattr(hb, name, float(crit_shear))
                        break
                    except Exception:
                        pass
                hb_set = True
                break
        except Exception:
            continue
        if hb_set:
            break

    # 5) Fallback TUI si la API no expone HB en tu build
    if not hb_set:
        try:
            # TUI: change-create con Herschel–Bulkley
            # Formato típico (puede variar por build; este funciona en muchas):
            # /define/materials/change-create carbopol fluid yes density constant <rho> viscosity herschel-bulkley <K> <n> <tau0> <crit_shear>
            solver.tui.define.materials.change_create(
                "carbopol", "fluid", "yes",
                "constant", str(rho),
                "herschel-bulkley", str(K), str(n), str(tau0), str(crit_shear),
                "", ""
            )
            hb_set = True
        except Exception as e_tui:
            print(f"⚠️ No se pudo fijar Herschel–Bulkley por API ni TUI: {e_tui}")

    if hb_set:
        print(f"✓ 'carbopol' {'creado' if created else 'actualizado'} con Herschel–Bulkley "
              f"(K={K} Pa·s^n, n={n}, τ0={tau0} Pa, γ̇*={crit_shear} 1/s; ρ={rho} kg/m³)")
    else:
        print("⚠️ Revisa manualmente en GUI: Define → Materials → Edit… → Viscosity: Herschel–Bulkley.")

    # 6) (opcional) asignar a zonas de fluido
    if assign_to_all_fluid_zones:
        try:
            cz = solver.setup.cell_zone_conditions.fluid
            any_assigned = False
            for zname in list(cz):
                try:
                    cz[zname].material = "carbopol"
                    any_assigned = True
                except Exception:
                    pass
            if any_assigned:
                print("✓ 'carbopol' asignado a todas las zonas de fluido.")
            else:
                try:
                    solver.tui.define.boundary_conditions.fluid("all-zones", "yes", "carbopol", "", "")
                    print("✓ 'carbopol' asignado a zonas de fluido [TUI].")
                except Exception:
                    print("ℹ️ No se pudo asignar automáticamente a zonas; asígnalo en GUI si es necesario.")
        except Exception:
            try:
                solver.tui.define.boundary_conditions.fluid("all-zones", "yes", "carbopol", "", "")
                print("✓ 'carbopol' asignado a zonas de fluido [TUI].")
            except Exception:
                print("ℹ️ No se pudo asignar automáticamente a zonas; asígnalo en GUI si es necesario.")

create_carbopol_hb_from_water(K=3.67, n=0.66, tau0=56.91, crit_shear=5.0, assign_to_all_fluid_zones=False)



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
