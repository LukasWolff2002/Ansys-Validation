import os
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
# Detectar las versiones de Fluent (AWP_ROOT251 y AWP_ROOT252)
# =========================
def get_fluent_path():
    # Primero intenta obtener la variable AWP_ROOT251
    awp_root_251 = os.environ.get('AWP_ROOT251')
    if awp_root_251:
        print("Usando Fluent versión 251 desde: ", awp_root_251)
        return awp_root_251

    # Si no encuentra AWP_ROOT251, intenta AWP_ROOT252
    awp_root_252 = os.environ.get('AWP_ROOT252')
    if awp_root_252:
        print("Usando Fluent versión 252 desde: ", awp_root_252)
        return awp_root_252

    # Si ninguna de las dos variables está configurada, lanza un error
    raise EnvironmentError("No se encontró ninguna instalación de Fluent. Configura las variables de entorno AWP_ROOT251 o AWP_ROOT252.")

# Obtener la ruta de Fluent basada en la variable de entorno disponible
fluent_path = get_fluent_path()

# =========================
# Lanzar Fluent (GUI)
# =========================
solver = launch_fluent(
    mode="solver",
    precision="double",
    processor_count=4,  # Puedes cambiar el número de procesadores si necesitas menos recursos
    ui_mode="gui",
    product_version="252",  # Si usas Fluent 252, usa esta versión. Si usas 251, cambia a "251"
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
# Forzar Multiphase = VOF
# =========================
def force_multiphase_and_define_phases_vof():
    # ================================================
    # 1) Forzar el modelo Multiphase = VOF
    # ================================================
    vof_ok = False
    try:
        # Configuración del modelo VOF en Settings API
        solver.settings.setup.models.multiphase.model = "vof"
        solver.settings.setup.models.multiphase.vof.formulation = "implicit"
        vof_ok = True
        print("✓ Multiphase = VOF (API, implicit)")
    except Exception as e:
        print(f"⚠️ API VOF no disponible o no se pudo configurar: {e}, probando TUI...")

    if not vof_ok:
        # Fallback TUI para VOF y Body Force
        try:
            solver.tui.define.models.multiphase("vof", "implicit")
            vof_ok = True
            print("✓ Multiphase = VOF (TUI, implicit body force)")
        except Exception as e:
            print(f"⚠️ No se pudo configurar VOF y Body Force con TUI: {e}")

    if not vof_ok:
        print("⚠️ No se pudo activar Multiphase = VOF o Implicit Body Force. Revisa en GUI: Define → Models → Multiphase → VOF.")

    # ================================================
    # 2) Definir Body Force Formulation = Implicit
    # ================================================
    body_force_ok = False
    try:
        solver.settings.setup.models.multiphase.body_force.formulation = "implicit"
        body_force_ok = True
        print("✓ Body Force Formulation = Implicit Body Force [Settings API]")
    except Exception as e:
        print(f"⚠️ No se pudo configurar Implicit Body Force en Settings API: {e}, probando TUI...")

    if not body_force_ok:
        # Fallback TUI para Implicit Body Force
        try:
            solver.tui.define.models.multiphase.body_force("implicit")
            body_force_ok = True
            print("✓ Body Force Formulation = Implicit Body Force [TUI]")
        except Exception as e:
            print(f"⚠️ No se pudo configurar Implicit Body Force en TUI: {e}")

    if not body_force_ok:
        print("⚠️ No se pudo configurar Implicit Body Force. Revisa en GUI: Define → Models → Multiphase → Body Force Formulation.")

    # ================================================
    # 3) Definir las fases
    # ================================================
    try:
        phases = solver.settings.setup.models.multiphase.phases
        # Definir fase de aire
        phases["air-phase"].material = "air"
        print("✓ air-phase material = air [Settings API]")

        # Definir fase de carbopol
        phases["carbopol-phase"].material = "carbopol"
        print("✓ carbopol-phase material = carbopol [Settings API]")
    except Exception as e:
        print(f"⚠️ Error configurando las fases: {e}")

    # Si falla la configuración de phases en Settings, intentamos con TUI:
    try:
        solver.tui.define.models.multiphase.phases("air-phase", "air")
        solver.tui.define.models.multiphase.phases("carbopol-phase", "carbopol")
        print("✓ Fases definidas con TUI: air-phase = air, carbopol-phase = carbopol.")
    except Exception as e:
        print(f"⚠️ No se pudieron configurar las fases con TUI: {e}")

# Llamar a la función
force_multiphase_and_define_phases_vof()

def initialize_solution():
    # =========================
    # 1) Inicializar las condiciones
    # =========================
    try:
        # Condiciones iniciales (puedes modificar según sea necesario)
        solver.settings.setup.general.solver.initialization = "standard"
        print("✓ Inicialización estándar aplicada (initialization = standard)")
    except Exception as e:
        print(f"⚠️ No se pudo aplicar inicialización estándar: {e}")

    # =========================
    # 2) Inicialización por TUI (fallback)
    # =========================
    try:
        solver.tui.solve.initialize("standard")
        print("✓ Inicialización realizada con TUI (standard initialization).")
    except Exception as e:
        print(f"⚠️ No se pudo inicializar por TUI: {e}")

    # =========================
    # 3) Comenzar la solución
    # =========================
    try:
        solver.tui.solve.iterate(100)  # Iterar 100 pasos como ejemplo
        print("✓ Solución iniciada con 100 iteraciones.")
    except Exception as e:
        print(f"⚠️ No se pudo iniciar la solución: {e}")

# Llamar a la función para inicializar la solución
initialize_solution()

def define_carbopol_region_for_patch():
    # Coordenadas de la región donde está la fase carbopol
    x_min, x_max = 0.0, 0.15
    y_min, y_max = -0.4, 0.4
    z_min, z_max = 0.0, 0.2

    # 1) Crear una zona de volumen para la región definida (usando TUI)
    try:
        solver.tui.define.create_box(
            "carbopol-region",  # Nombre de la zona
            x_min, x_max,       # Coordenadas X
            y_min, y_max,       # Coordenadas Y
            z_min, z_max        # Coordenadas Z
        )
        print(f"✓ Región 'carbopol-region' creada entre X({x_min},{x_max}), Y({y_min},{y_max}), Z({z_min},{z_max})")
    except Exception as e:
        print(f"⚠️ Error creando la región con TUI: {e}")

    # 2) Asignar el material 'carbopol' a la región (usando TUI)
    try:
        # Asegurémonos de que el material "carbopol" ya ha sido creado
        solver.tui.define.materials.change_create(
            "carbopol", "fluid", "yes",
            "constant", "998.2",  # ejemplo de densidad constante
            "herschel-bulkley", "3.67", "0.66", "56.91", "5.0", "", ""
        )
        solver.tui.define.zone_material("carbopol-region", "carbopol")
        print(f"✓ Material 'carbopol' asignado a la región 'carbopol-region'.")
    except Exception as e:
        print(f"⚠️ No se pudo asignar el material 'carbopol' a la región: {e}")

    # 3) (Alternativa) Usar Settings API para la región (si TUI falla)
    try:
        # Acceder a la zona de celdas
        zone = solver.settings.setup.cell_zone_conditions
        # Crear una nueva zona de celdas (por ejemplo, 'carbopol-region')
        zone.create("carbopol-region")
        zone["carbopol-region"].material = "carbopol"
        print("✓ Región 'carbopol-region' creada y material 'carbopol' asignado [Settings API].")
    except Exception as e:
        print(f"⚠️ No se pudo crear la región con Settings API: {e}")

# Llamar a la función para crear la región de 'carbopol'
define_carbopol_region_for_patch()

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
