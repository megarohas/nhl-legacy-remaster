// Импорты ядра, которых нет в готовой сборке rexruntime 0.10.0 (win-amd64).
// В исходниках SDK v0.10.0 камера есть (src/kernel/xboxkrnl/xboxkrnl_usbcam.cpp),
// но в DLL и её библиотеке импорта этих экспортов нет — без них не линкуется.

#include <rex/hook.h>

// Камера Xbox Live Vision: «не подключена», как XUsbcamGetState_entry в SDK.
REX_EXPORT_STUB_RETURN(__imp__XUsbcamGetState, 0)

// Камеры нет — X_ERROR_DEVICE_NOT_CONNECTED.
REX_EXPORT_STUB_RETURN(__imp__XUsbcamSetConfig, 0x48F)
