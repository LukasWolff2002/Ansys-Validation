from ansys.fluent.core import launch_fluent
import time
from pathlib import Path

# =========================
# Rutas (relativas al script)
# =========================
base_dir = Path(__file__).resolve().parent
case = base_dir / "WorkBench_files" / "dp0" / "FFF" / "Fluent" / "FFF-Setup-Output.cas.h5"
setf = base_dir / "WorkBench_files" / "dp0" / "FFF" / "Fluent" / "FFF.set"
data = case.with_suffix(".dat.h5")  # si existe, en general NO lo cargaremos si cambiamos el setup

# =========================
# Lanzar Fluent (GUI)
# =========================
solver = launch_fluent(
    mode="solver",
    precision="double",
    processor_count=4,
    ui_mode="gui",
    product_version="25.1.0",
)

# =========================
# Abrir case y (opcional) settings
# =========================
solver.tui.file.read_case(str(case))

if setf.exists():
    # Nota: aplicar .set puede sobreescribir modelos/zonas. Si no lo necesitas, comenta esta línea.
    solver.tui.file.read_settings(str(setf))
    print(f"Settings aplicados desde: {setf}")

# ==============================================
# Forzar modelos: Energy + Laminar + Transient + Gravedad Z
# ==============================================
def force_models_energy_laminar_gravity_transient():
    # Energy ON + Laminar (Settings API)
    ms = solver.settings.setup.models
    ms.energy.enabled = True
    ms.viscous.model = "laminar"
    print("✓ Energy=ON, Viscous=Laminar")

    # Time = Transient con un esquema válido
    solver.settings.setup.general.solver.time = "unsteady-2nd-order"
    print("✓ Solver → Transient (unsteady-2nd-order)")

    # Gravedad en Z (0, 0, -9.81)
    gravity_ok = False
    try:
        # Setup API
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
        try:
            solver.tui.define.operating_conditions.gravity("yes", "0", "0", "-9.81")
            print("✓ Gravedad ON (0, 0, -9.81) [TUI]")
        except Exception as e:
            print(f"⚠️ No se pudo fijar gravedad automáticamente: {e}")

force_models_energy_laminar_gravity_transient()

# ===================================================
# Material: carbopol (Herschel–Bulkley desde water)
# ===================================================
def create_carbopol_hb_from_water(K=3.67, n=0.66, tau0=56.91, crit_shear=5.0, assign_to_all_fluid_zones=False):
    """
    Crea/actualiza 'carbopol' basado en 'water-liquid' y define viscosidad Herschel–Bulkley:
      K [Pa·s^n], n [-], tau0 [Pa], critical shear rate [1/s].
    Copia densidad del agua si es posible; si no, usa 998.2 kg/m³.
    """
    rho_default = 998.2
    rho = rho_default

    # 1) Densidad de water-liquid (setup -> settings)
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

    # 2) Crear/copiar 'carbopol'
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

    # 3) Densidad constante
    try:
        material_obj.density.option = "constant"
    except Exception:
        pass
    try:
        material_obj.density.value = float(rho)
    except Exception:
        pass

    # 4) Viscosidad Herschel–Bulkley (API variantes + Threshold)
    hb_set = False
    candidates = []
    try:
        candidates.append(material_obj.viscosity)  # setup API
    except Exception:
        pass
    try:
        candidates.append(solver.settings.setup.materials.fluid["carbopol"].viscosity)  # settings API
    except Exception:
        pass

    for vis in candidates:
        try:
            # Selección del modelo HB (nombres posibles según build)
            for opt in ("herschel-bulkley", "herschel_bulkley", "herschelbulkley", "herschel-bulkley-regularized"):
                try:
                    vis.option = opt
                    break
                except Exception:
                    continue

            # Nodo HB (según build)
            hb_nodes = [
                getattr(vis, "herschel_bulkley", None),
                getattr(vis, "herschelbulkley", None),
                getattr(vis, "herschel_b", None),
                vis  # a veces cuelga directo
            ]
            for hb in hb_nodes:
                if hb is None:
                    continue

                # K (consistency index)
                for name in ("consistency_index", "k", "consistency", "consistencyindex"):
                    try:
                        setattr(hb, name, float(K))
                        break
                    except Exception:
                        pass

                # n (power-law index)
                for name in ("power_law_index", "n", "powerindex", "power_index"):
                    try:
                        setattr(hb, name, float(n))
                        break
                    except Exception:
                        pass

                # τ0 (yield stress)
                for name in ("yield_stress", "tau0", "yieldstress"):
                    try:
                        setattr(hb, name, float(tau0))
                        break
                    except Exception:
                        pass

                # Yield Stress Threshold (si existe en tu build)
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
            # /define/materials/change-create carbopol fluid yes density constant <rho>
            #    viscosity herschel-bulkley <K> <n> <tau0> <crit_shear>
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
        print(f"✓ 'carbopol' {'creado' if created else 'actualizado'} (HB: K={K} Pa·s^n, n={n}, τ0={tau0} Pa, γ̇*={crit_shear} s⁻¹; ρ={rho} kg/m³)")
    else:
        print("⚠️ Revisa en GUI: Define → Materials → Edit… → Viscosity: Herschel–Bulkley.")

    # 6) (opcional) asignarlo a zonas de fluido
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
                    print("ℹ️ No se pudo asignar automáticamente; asígnalo en GUI si es necesario.")
        except Exception:
            try:
                solver.tui.define.boundary_conditions.fluid("all-zones", "yes", "carbopol", "", "")
                print("✓ 'carbopol' asignado a zonas de fluido [TUI].")
            except Exception:
                print("ℹ️ No se pudo asignar automáticamente; asígnalo en GUI si es necesario.")

# Crear/actualizar material (sin asignar automáticamente a zonas)
create_carbopol_hb_from_water(K=3.67, n=0.66, tau0=56.91, crit_shear=5.0, assign_to_all_fluid_zones=False)

# =========================
# (Opcional) No cargar data si cambió el setup
# =========================
if data.exists():
    print(f"⚠️ Se encontró {data.name}, pero NO se cargará porque se modificó el setup "
          f"(modelos/condiciones). Cargar datos con setup distinto puede ser inconsistente.")

# =========================
# Mostrar malla y mantener vivo
# =========================
try:
    solver.tui.display.mesh()
except Exception:
    pass

print("✅ Case cargado, modelos/condiciones forzados y 'carbopol' definido. Deja esta consola abierta.")

# Mantener vivo mientras Fluent esté abierto
try:
    while True:
        try:
            # API moderna para health check
            if hasattr(solver, "is_server_healthy"):
                if not solver.is_server_healthy():
                    print("🔻 Fluent se ha cerrado. Finalizando script.")
                    break
            else:
                # compatibilidad con versiones antiguas
                solver.health_check.check_health()
        except Exception:
            print("🔻 Fluent se ha cerrado. Finalizando script.")
            break
        time.sleep(2)
except KeyboardInterrupt:
    print("⏹ Interrumpido por el usuario. Cerrando script.")
