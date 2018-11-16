# -*- coding: utf-8 -*-

import inspect
import sys
import logging
from construct import *
from .adapters import *
from ..panel import Panel as PanelBase
from ..common import CommunicationSourceIDEnum, ProductIdEnum, calculate_checksum

MEM_ZONE_START = 0x010
MEM_ZONE_END = MEM_ZONE_START + 0x10 * 32
MEM_OUTPUT_START = MEM_ZONE_END
MEM_OUTPUT_END = MEM_OUTPUT_START + 0x10 * 16
MEM_PARTITION_START = MEM_OUTPUT_END
MEM_PARTITION_END = MEM_PARTITION_START + 0x10 * 2
MEM_USER_START = MEM_PARTITION_END
MEM_USER_END = MEM_USER_START + 0x10 * 32
MEM_BUS_START = MEM_USER_END
MEM_BUS_END = MEM_BUS_START + 0x10 * 15
MEM_REPEATER_START = MEM_BUS_END
MEM_REPEATER_END = MEM_REPEATER_START + 0x10 * 2
MEM_KEYPAD_START = MEM_REPEATER_END
MEM_KEYPAD_END = MEM_KEYPAD_START + 0x10 * 8
MEM_SITE_START = MEM_KEYPAD_END
MEM_SITE_END = MEM_SITE_START + 0x10
MEM_SIREN_START = MEM_SITE_END
MEM_SIREN_END = MEM_SIREN_START + 0x10 * 4

logger = logging.getLogger('PAI').getChild(__name__)


class Panel(PanelBase):
    def get_message(self, name):
        try:
            return super(Panel, self).get_message(name)
        except ResourceWarning as e:
            clsmembers = dict(inspect.getmembers(sys.modules[__name__]))
            if name in clsmembers:
                return clsmembers[name]
            else:
                raise e

    def update_labels(self):
        logger.info("Updating Labels from Panel")

        output_template = dict(
            on=False,
            pulse=False)

        self.load_labels(self.core.zones, self.core.labels['zone'], MEM_ZONE_START, MEM_ZONE_END)
        logger.info("Zones: {}".format(', '.join(self.core.labels['zone'])))
        self.load_labels(self.core.outputs, self.core.labels['output'], MEM_OUTPUT_START, MEM_OUTPUT_END,
                         template=output_template)
        logger.info("Outputs: {}".format(', '.join(list(self.core.labels['output']))))
        self.load_labels(self.core.partitions, self.core.labels['partition'], MEM_PARTITION_START, MEM_PARTITION_END)
        logger.info("Partitions: {}".format(', '.join(list(self.core.labels['partition']))))
        self.load_labels(self.core.users, self.core.labels['user'], MEM_USER_START, MEM_USER_END)
        logger.info("Users: {}".format(', '.join(list(self.core.labels['user']))))
        self.load_labels(self.core.buses, self.core.labels['bus'], MEM_BUS_START, MEM_BUS_END)
        logger.info("Buses: {}".format(', '.join(list(self.core.labels['bus']))))
        self.load_labels(self.core.repeaters, self.core.labels['repeater'], MEM_REPEATER_START, MEM_REPEATER_END)
        logger.info("Repeaters: {}".format(', '.join(list(self.core.labels['repeater']))))
        self.load_labels(self.core.keypads, self.core.labels['keypad'], MEM_KEYPAD_START, MEM_KEYPAD_END)
        logger.info("Keypads: {}".format(', '.join(list(self.core.labels['keypad']))))
        self.load_labels(self.core.sites, self.core.labels['site'], MEM_SITE_START, MEM_SITE_END)
        logger.info("Sites: {}".format(', '.join(list(self.core.labels['site']))))
        self.load_labels(self.core.sirens, self.core.labels['siren'], MEM_SIREN_START, MEM_SIREN_END)
        logger.info("Sirens: {}".format(', '.join(list(self.core.labels['siren']))))

        logger.debug("Labels updated")

    def load_labels(self,
                    labelDictIndex,
                    labelDictName,
                    start,
                    end,
                    limit=range(1, 33),
                    template=dict(label='')):
        """Load labels from panel"""
        i = 1
        address = start

        if len(limit) == 0:
            return

        while address < end and i <= max(limit):
            args = dict(address=address)
            reply = self.core.send_wait(self.get_message('ReadEEPROM'), args, reply_expected=0x05)

            if reply is None:
                logger.error("Could not fully load labels")
                return

            # Avoid errors due to colision with events
            if reply.fields.value.address != address:
                continue

            payload = reply.fields.value.data
            label = payload[:16].strip(b'\0 ').replace(b'\0', b'_').replace(b' ', b'_').decode('utf-8')

            if label not in labelDictName and i in limit:
                properties = template.copy()
                properties['label'] = label
                labelDictIndex[i] = properties

                labelDictName[label] = i
            i += 1

            address += 16

    def parse_message(self, message):
        try:
            if message is None or len(message) == 0:
                return None

            if message[0] == 0x70:
                return CloseConnection.parse(message)
            elif message[0] >> 4 == 0x7:
                return ErrorMessage.parse(message)
            elif message[0] == 0x00:
                return InitializeCommunication.parse(message)
            elif message[0] == 0x10:
                return InitializeCommunicationResponse.parse(message)
            elif message[0] == 0x30:
                return SetTimeDate.parse(message)
            elif message[0] >> 4 == 0x03:
                return SetTimeDateResponse.parse(message)
            elif message[0] == 0x40:
                return PerformAction.parse(message)
            elif message[0] >> 4 == 4:
                return PerformActionResponse.parse(message)
            elif message[0] == 0x50 and message[2] == 0x80:
                return PanelStatus.parse(message)
            elif message[0] == 0x50 and message[2] < 0x80:
                return ReadEEPROM.parse(message)
            elif message[0] >> 4 == 0x05 and message[2] == 0x80:
                return PanelStatusResponse[message[3]].parse(message)
            elif message[0] >> 4 == 0x05 and message[2] < 0x80:
                return ReadEEPROMResponse.parse(message)
            #        elif message[0] == 0x60 and message[2] < 0x80:
            #            return WriteEEPROM.parse(message)
            #        elif message[0] >> 4 == 0x06 and message[2] < 0x80:
            #            return WriteEEPROMResponse.parse(message)
            elif message[0] >> 4 == 0x0e:
                return LiveEvent.parse(message)
            else:
                logger.warn("Unknown message")
        except Exception:
            logger.exception("Parsing message")

        s = 'PARSE: '
        for c in message:
            s += "{:02x} ".format(c)

        logger.debug(s)

        return None

    def initialize_communication(self, reply, PASSWORD):
        password = self.encode_password(PASSWORD)

        args = dict(product_id=reply.fields.value.product_id,
                    firmware=reply.fields.value.firmware,
                    panel_id=reply.fields.value.panel_id,
                    pc_password=password,
                    user_code=0x000000,
                    not_used1=0x19,
                    source_id=0x02
                    )

        logger.info("Initializing communication")
        reply = self.core.send_wait(self.get_message('InitializeCommunication'), args=args)

        if reply is None:
            return False

        if reply.fields.value.po.command == 0x10:
            logger.info("Authentication Success")
            return True
        elif reply.fields.value.po.command == 0x07 or reply.fields.value.po.command == 0x00:
            logger.error("Authentication Failed. Wrong Password?")
            return False


InitializeCommunication = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x00, Int8ub)),
        "not_used0" / Padding(3),
        "product_id" / ProductIdEnum,
        "firmware" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "build" / Int8ub),
        "panel_id" / Int16ub,
        "pc_password" / Default(Bytes(2), b'0000'),
        "not_used1" / Bytes(1),
        "source_method" / Default(Enum(Int8ub,
                                       Winload_Connection=0x00,
                                       NEware_Connection=0x55), 0x00),
        "user_code" / Default(Int32ub, 0x00000000),
        "not_used2" / Padding(15),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_id" / Struct(
            "high" / Default(Int8ub, 0),
            "low" / Default(Int8ub, 0)),
    )),
                                 "checksum" / Checksum(
                                     Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

InitializeCommunicationResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x10, Int8ub)),
        "neware_connection" / Int16ub,
        "user_id_low" / Int8ub,
        "partition_rights" / BitStruct(
            "not_used" / BitsInteger(6),
            "partition_2" / Flag,
            "partition_1" / Flag),
        "not_used0" / Padding(31),
    )),
                                         "checksum" / Checksum(
                                             Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

PanelStatus = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x50, Int8ub)),
        "not_used0" / Default(Int8ub, 0x00),
        "validation" / Default(Int8ub, 0x00),
        "status_request" / Default(Int8ub, 0x00),
        "not_used0" / Padding(29),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
    )),
                     Padding(31),
                     "checksum" / Checksum(
                         Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

PanelStatusResponse = [
    Struct("fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)
        ),
        "not_used0" / Padding(1),
        "validation" / Const(0x80, Int8ub),
        "status_request" / Const(0, Int8ub),
        "troubles" / BitStruct(
            "timer_loss_trouble" / Flag,
            "fire_loop_trouble" / Flag,
            "module_tamper_trouble" / Flag,
            "zone_tamper_trouble" / Flag,
            "communication_trouble" / Flag,
            "bell_trouble" / Flag,
            "power_trouble" / Flag,
            "rf_low_battery_trouble" / Flag,
            "rf_interference_trouble" / Flag,
            "not_used0" / BitsInteger(5),
            "module_supervision_trouble" / Flag,
            "zone_supervision_trouble" / Flag,
            "not_used0" / BitsInteger(1),
            "wireless_repeater_battery_trouble" / Flag,
            "wireless_repeater_ac_loss_trouble" / Flag,
            "wireless_leypaad _battery_trouble" / Flag,
            "wireless_leypad_ac_trouble" / Flag,
            "auxiliary_output_overload_trouble" / Flag,
            "ac_failure_trouble" / Flag,
            "low_battery_trouble" / Flag,
            "not_used1" / BitsInteger(6),
            "bell_output_overload_trouble" / Flag,
            "bell_output_disconnected_trouble" / Flag,
            "not_used2" / BitsInteger(2),
            "computer_fail_to_communicate_trouble" / Flag,
            "voice_fail_to_communicate_trouble" / Flag,
            "pager_fail_to_communicate_trouble" / Flag,
            "central_2_reporting_ftc_indicator_trouble" / Flag,
            "central_1_reporting_ftc_indicator_trouble" / Flag,
            "telephone_line" / Flag),
        "time" / DateAdapter(Bytes(6)),
        "vdc" / ExprAdapter(Byte, obj_ * (20.3 - 1.4) / 255.0 + 1.4, 0),
        "dc" / ExprAdapter(Byte, obj_ * 22.8 / 255.0, 0),
        "battery" / ExprAdapter(Byte, obj_ * 22.8 / 255.0, 0),
        "rf_noise_floor" / Int8ub,
        "zone_open" / StatusAdapter(Bytes(4)),
        "zone_tamper" / StatusAdapter(Bytes(4)),
        "pgm_tamper" / StatusAdapter(Bytes(2)),
        "bus_tamper" / StatusAdapter(Bytes(2)),
        "zone_fire" / StatusAdapter(Bytes(4)),
        "not_used1" / Int8ub)),
           "checksum" / Checksum(
               Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
    ,
    Struct("fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Padding(1),
        "validation" / Const(0x80, Int8ub),
        "status_request" / Const(1, Int8ub),
        "zone_rf_supervision_trouble" / StatusAdapter(Bytes(4)),
        "pgm_supervision_trouble" / StatusAdapter(Bytes(2)),
        "bus_supervision_trouble" / StatusAdapter(Bytes(2)),
        "wireless-repeater_supervision_trouble" / StatusAdapter(Bytes(1)),
        "zone_rf_low_battery_trouble" / StatusAdapter(Bytes(4)),
        "partition_status" / PartitionStatusAdapter(Bytes(8)),
        "wireless-repeater_ac_loss_trouble" / StatusAdapter(Bytes(1)),
        "wireless-repeater_battery_failure_trouble" / StatusAdapter(Bytes(1)),
        "wireless-keypad_ac_loss_trouble" / StatusAdapter(Bytes(1)),
        "wireless-keypad_battery_failure_trouble" / StatusAdapter(Bytes(1)),
        "wireless-keypad_supervision_failure_trouble" / StatusAdapter(Bytes(1)),
        "not_used1" / Padding(6)
    )),
           "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
    ,
    Struct("fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Padding(1),
        "validation" / Const(0x80, Int8ub),
        "status_request" / Const(2, Int8ub),
        "zone_status" / ZoneStatusAdapter(Bytes(32))
    )),
           "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
    ,
    Struct("fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Padding(1),
        "validation" / Const(0x80, Int8ub),
        "status_request" / Const(3, Int8ub),
        "zone_signal_strength" / SignalStrengthAdapter(Bytes(32))
    )),
           "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
    ,
    Struct("fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Padding(1),
        "validation" / Const(0x80, Int8ub),
        "status_request" / Const(4, Int8ub),
        "pgm_signal_strength" / SignalStrengthAdapter(Bytes(16)),
        "wireless-repeater_signal_strength" / SignalStrengthAdapter(Bytes(2)),
        "wireless-keypad_signal_strength" / SignalStrengthAdapter(Bytes(8)),
        "not_used1" / Padding(6)
    )),
           "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
    ,
    Struct("fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Padding(1),
        "validation" / Const(0x80, Int8ub),
        "status_request" / Const(5, Int8ub),
        "zone_exit_delay" / StatusAdapter(Bytes(4)),
        "not_used1" / Padding(28)
    )),
           "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
]

LiveEvent = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0xE, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "time" / DateAdapter(Bytes(6)),
        "event" / EventAdapter(Bytes(2)),
        "partition" / ExprAdapter(Byte, obj_ + 1, obj_ - 1),
        "module_serial" / ModuleSerialAdapter(Bytes(4)),
        "label_type" / Bytes(1),
        "label" / Bytes(16),
        "unknown" / Bytes(1),
        "reserved2" / Bytes(4),
    )), "checksum" / Checksum(
    Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

Action = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct(
            "command" / Const(0x40, Int8ub),
        ),
        "not_used0" / Default(Int8ub, 0),
        "action" / Enum(Int8ub,
                        Stay_Arm=0x1,
                        Stay_Arm1=0x2,
                        Sleep_Arm=0x3,
                        Full_Arm=0x4,
                        Disarm=0x5,
                        Stay_Arm_D_Enabled=0x6,
                        Stay_Arm_Sleep_D_Enabled=0x7,
                        Disarm_Both=0x8,
                        Bypass=0x10,
                        Beep=0x20,
                        PGM_On_Override=0x30,
                        PGM_Off_Override=0x31,
                        PGM_On=0x32,
                        PGM_Off=0x33,
                        Reload_RAM=0x80),
        "argument" / ExprAdapter(Byte, obj_ + 1, obj_ - 1),
        "not_used0" / Padding(29),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
    )),
                "checksum" / Checksum(
                    Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ActionResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x4, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Default(Int8ub, 0),
        "not_used1" / Default(Int8ub, 0),
        "action" / Int8ub,
    )),
                        "reserved0" / Padding(32),
                        "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

CloseConnection = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct(
            "command" / Const(0x70, Int8ub)
        ),
        "not_used0" / Const(0, Int8ub),
        "validation_byte" / Default(Int8ub, 0),
        "not_used1" / Padding(29),
        "message" / Default(Enum(Int8ub,
                                 authentication_failed=0x12,
                                 panel_will_disconnect=0x05), 0x05),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
    )),
                         "checksum" / Checksum(
                             Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ErrorMessage = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x7, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Default(Int8ub, 0),
        "message" / Enum(Int8ub,
                         requested_command_failed=0x00,
                         invalid_user_code=0x01,
                         partition_in_code_lockout=0x02,
                         panel_will_disconnect=0x05,
                         panel_not_connected=0x10,
                         panel_already_connected=0x11,
                         invalid_pc_password=0x12,
                         winload_on_phone_line=0x13,
                         invalid_module_address=0x14,
                         cannot_write_in_ram=0x15,
                         upgrade_request_fail=0x16,
                         record_number_out_of_range=0x17,
                         invalid_record_type=0x19,
                         multibus_not_supported=0x1a,
                         incorrect_number_of_users=0x1b,
                         invalid_label_number=0x1c
                         ),
        "not_used1" / Padding(33),
    )),
                      "checksum" / Checksum(
                          Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ReadEEPROM = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x50, Int8ub)),
        "not_used0" / Padding(1),
        "address" / Default(Int16ub, 0),
        "not_used0" / Padding(29),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
    )),
                    "checksum" / Checksum(
                        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ReadEEPROMResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x5, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Padding(1),
        "address" / Default(Int16ub, 0),
        "data" / Bytes(32),
    )),
                            "checksum" / Checksum(
                                Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

SetTimeDate = Struct("fields" / RawCopy(Struct(
    "po" / Struct(
        "command" / Const(0x30, Int8ub)),
    "not_used0" / Padding(3),
    "century" / Int8ub,
    "year" / Int8ub,
    "month" / Int8ub,
    "day" / Int8ub,
    "hour" / Int8ub,
    "minute" / Int8ub,
    "not_used1" / Padding(23),
    "source_id" / Default(CommunicationSourceIDEnum, 1),
    "user_high" / Default(Int8ub, 0),
    "user_low" / Default(Int8ub, 0),
)),
                     "checksum" / Checksum(
                         Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

SetTimeDateResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x3, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Padding(35),
    )),
                             "checksum" / Checksum(
                                 Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

PerformAction = Struct("fields" / RawCopy(Struct(
    "po" / Struct(
        "command" / Const(0x40, Int8ub)),
    "not_used0" / Padding(1),
    "action" / Enum(Int8ub,
                    Stay_Arm=0x01,
                    Stay_Arm1=0x02,
                    Sleep_Arm=0x03,
                    Full_Arm=0x04,
                    Disarm=0x05,
                    Stay_Arm_StayD=0x06,
                    Sleep_Arm_StayD=0x07,
                    Disarm_Both_Disable_StayD=0x08,
                    Bypass=0x10,
                    Beep=0x10,
                    PGM_On_Override=0x30,
                    PGM_Off_Override=0x31,
                    PGM_On=0x32,
                    PGM_Off=0x33,
                    Reload_RAM=0x80,
                    Bus_Scan=0x85,
                    Future_Use=0x90),
    "argument" / Enum(Int8ub,
                      One_Beep=0x04,
                      Fail_Beep=0x08,
                      Beep_Twice=0x0c,
                      Accept_Beep=0x10),
    "not_used1" / Padding(29),
    "source_id" / Default(CommunicationSourceIDEnum, 1),
    "user_high" / Default(Int8ub, 0),
    "user_low" / Default(Int8ub, 0),
)),
                       "checksum" / Checksum(
                           Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

PerformActionResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x4, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Padding(1),
        "action" / Enum(Int8ub,
                        Stay_Arm=0x01,
                        Stay_Arm1=0x02,
                        Sleep_Arm=0x03,
                        Full_Arm=0x04,
                        Disarm=0x05,
                        Stay_Arm_StayD=0x06,
                        Sleep_Arm_StayD=0x07,
                        Disarm_Both_Disable_StayD=0x08,
                        Bypass=0x10,
                        Beep=0x10,
                        PGM_On_Override=0x30,
                        PGM_Off_Overrite=0x31,
                        PGM_On=0x32,
                        PGM_Of=0x33,
                        Reload_RAM=0x80,
                        Bus_Scan=0x85,
                        Future_Use=0x90),
        "not_used1" / Padding(33),
    )),
                               "checksum" / Checksum(
                                   Bytes(1), lambda data: calculate_checksum(data), this.fields.data))