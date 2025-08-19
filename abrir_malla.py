from ansys.fluent.core import launch_fluent
import time
from pathlib import Path

# Ruta base = carpeta donde está este script
base_dir = Path(__file__).resolve().parent

# Archivos relativos al proyecto
case = base_dir / "WorkBench_files" / "dp0" / "FFF" / "Fluent" / "FFF-Setup-Output.cas.h5"
setf = base_dir / "WorkBench_files" / "dp0" / "FFF" / "Fluent" / "FFF.set"
data = case.with_suffix(".dat.h5")  # por si existe un .dat.h5 junto al .cas.h5

solver = launch_fluent(
    mode="solver",
    precision="double",
    processor_count=4,
    ui_mode="gui",
    product_version="25.1.0",
)

# 1) Abrir el case
solver.tui.file.read_case(str(case))

# 2) (Opcional) cargar resultados si existe .dat.h5
if data.exists():
    solver.tui.file.read_data(str(data))
    print("Resultados cargados desde:", data)

# 3) (Opcional) aplicar settings si existe .set
if setf.exists():
    solver.tui.file.read_settings(str(setf))
    print("Settings aplicados desde:", setf)

# 4) Mostrar malla
solver.tui.display.mesh()

print("✅ Case cargado, malla mostrada. Deja esta consola abierta.")

# 5) Mantener vivo mientras Fluent esté abierto
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
