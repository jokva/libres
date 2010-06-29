
from fetcher import PlotDataFetcherHandler
from pages.config.parameters.parametermodels import FieldModel, SummaryModel, KeywordModel, DataModel
import ertwrapper
import enums
from PyQt4.QtGui import QWidget, QFormLayout, QSpinBox, QComboBox
from PyQt4.QtCore import SIGNAL
from erttypes import time_t
import numpy

class EnsembleFetcher(PlotDataFetcherHandler):

    def __init__(self):
        PlotDataFetcherHandler.__init__(self)
        
        self.field_configuration = FieldConfigurationWidget()
        self.summary_configuration = SummaryConfigurationWidget()
        self.keyword_configuration = KeywordConfigurationWidget()

        def emitter():
            self.emit(SIGNAL('dataChanged()'))

        self.connect(self.field_configuration, SIGNAL('configurationChanged()'), emitter)
        self.connect(self.summary_configuration, SIGNAL('configurationChanged()'), emitter)
        self.connect(self.keyword_configuration, SIGNAL('configurationChanged()'), emitter)

    def initialize(self, ert):
        ert.prototype("long ensemble_config_get_node(long, char*)")
        ert.prototype("bool ensemble_config_has_key(long, char*)")

        ert.prototype("long enkf_main_get_fs(long)")
        ert.prototype("int enkf_main_get_ensemble_size(long)")
        ert.prototype("long enkf_main_iget_member_config(long, int)")
        ert.prototype("void enkf_main_get_observations(long, char*, int, long*, double*, double*)") #main, user_key, *time, *y, *std
        ert.prototype("int enkf_main_get_observation_count(long, char*)")

        ert.prototype("bool enkf_fs_has_node(long, long, int, int, int)")
        ert.prototype("void enkf_fs_fread_node(long, long, int, int, int)")

        ert.prototype("long enkf_node_alloc(long)")
        ert.prototype("void enkf_node_free(long)")
        ert.prototype("double enkf_node_user_get(long, char*, bool*)")

        ert.prototype("double member_config_iget_sim_days(long, int, int)")
        ert.prototype("time_t member_config_iget_sim_time(long, int, int)")
        ert.prototype("int member_config_get_last_restart_nr(long)")

        ert.prototype("long enkf_config_node_get_ref(long)")
        ert.prototype("bool field_config_ijk_active(long, int, int, int)")

        ert.prototype("bool ecl_sum_has_general_var(long, char*)", lib=ert.ecl)
        ert.prototype("int ecl_sum_get_general_var_index(long, char*)", lib=ert.ecl)

        ert.prototype("time_vector ecl_sum_alloc_time_vector(long, bool)", lib=ert.ecl)
        ert.prototype("double_vector ecl_sum_alloc_data_vector(long, int, bool)", lib=ert.ecl)


    def isHandlerFor(self, ert, key):
        return ert.enkf.ensemble_config_has_key(ert.ensemble_config, key)


    def fetch(self, ert, key, parameter, data):
        data.x_data_type = "time"

        fs = ert.enkf.enkf_main_get_fs(ert.main)
        config_node = ert.enkf.ensemble_config_get_node(ert.ensemble_config, key)
        node = ert.enkf.enkf_node_alloc(config_node)
        num_realizations = ert.enkf.enkf_main_get_ensemble_size(ert.main)

        user_data = parameter.getUserData()

        if user_data is None:
            return False

        key_index = None
        if user_data.has_key('key_index'):
            key_index = user_data['key_index']

        if parameter.getType() == FieldModel.TYPE:
            field_position = user_data['field_position']
            field_config = ert.enkf.enkf_config_node_get_ref(config_node)
            if ert.enkf.field_config_ijk_active(field_config, field_position[0] - 1, field_position[1] - 1, field_position[2] - 1):
                key_index = "%i,%i,%i" % (field_position[0], field_position[1], field_position[2])
                data.setKeyIndexIsIndex(True)
            else:
                return False

        data.setKeyIndex(key_index)

        state_list = [user_data['state']]
        if state_list[0] == enums.ert_state_enum.BOTH:
            state_list = [enums.ert_state_enum.FORECAST, enums.ert_state_enum.ANALYZED]

        for member in range(0, num_realizations):
            data.x_data[member] = []
            data.y_data[member] = []
            x_time = data.x_data[member]
            y = data.y_data[member]

            member_config = ert.enkf.enkf_main_iget_member_config(ert.main, member)
            stop_time = ert.enkf.member_config_get_last_restart_nr(member_config)

            for step in range(0, stop_time + 1):
                for state in state_list:
                    if ert.enkf.enkf_fs_has_node(fs, config_node, step, member, state.value()):
                        sim_time = ert.enkf.member_config_iget_sim_time(member_config, step, fs)
                        ert.enkf.enkf_fs_fread_node(fs, node, step, member, state.value())
                        valid = ertwrapper.c_int()
                        value = ert.enkf.enkf_node_user_get(node, key_index, ertwrapper.byref(valid))
                        if valid.value == 1:
                            data.checkMaxMin(sim_time)
                            data.checkMaxMinY(value)
                            x_time.append(sim_time)
                            y.append(value)
                        else:
                            print "Not valid: ", key, member, step, key_index

            data.x_data[member] = numpy.array([t.datetime() for t in x_time])
            data.y_data[member] = numpy.array(y)


        self.getObservations(ert, key, key_index, data)

        self.getRefCase(ert, key, data)

        ert.enkf.enkf_node_free(node)

        data.inverted_y_axis = False

    def getObservations(self, ert, key, key_index, data):
        if not key_index is None:
            user_key = "%s:%s" % (key, key_index)
        else:
            user_key = key

        obs_count = ert.enkf.enkf_main_get_observation_count(ert.main, user_key)
        if obs_count > 0:
            obs_x = (time_t * obs_count)()
            obs_y = (ertwrapper.c_double * obs_count)()
            obs_std = (ertwrapper.c_double * obs_count)()
            ert.enkf.enkf_main_get_observations(ert.main, user_key, obs_count, obs_x, obs_y, obs_std)

            data.obs_x = numpy.array([t.datetime() for t in obs_x])
            data.obs_y = numpy.array(obs_y)
            data.obs_std_y = numpy.array(obs_std)
            data.obs_std_x = None

            data.checkMaxMin(max(obs_x))
            data.checkMaxMin(min(obs_x))

            data.checkMaxMinY(max(obs_y))
            data.checkMaxMinY(min(obs_y))


    def getRefCase(self, ert, key, data):
        ecl_sum = ert.enkf.ecl_config_get_refcase(ert.ecl_config)

        if(ert.ecl.ecl_sum_has_general_var(ecl_sum, key)):
            ki = ert.ecl.ecl_sum_get_general_var_index(ecl_sum, key)
            x_data = ert.ecl.ecl_sum_alloc_time_vector(ecl_sum, True)
            y_data = ert.ecl.ecl_sum_alloc_data_vector(ecl_sum, ki, True)

            data.refcase_x = []
            data.refcase_y = []
            first = True
            for x in x_data:
                if not first:
                    data.refcase_x.append(x)
                    data.checkMaxMin(x)
                else:
                    first = False #skip first element because of eclipse behavior

            first = True
            for y in y_data:
                if not first:
                    data.refcase_y.append(y)
                    data.checkMaxMinY(y)
                else:
                    first = False #skip first element because of eclipse behavior

            data.refcase_x = numpy.array([t.datetime() for t in data.refcase_x])
            data.refcase_y = numpy.array(data.refcase_y)

    def configure(self, parameter, context_data):
        self.parameter = parameter

        cw = self.getConfigurationWidget(context_data)
        if not cw is None:
            cw.setParameter(parameter)

    def getConfigurationWidget(self, context_data):
        if self.parameter.getType() == SummaryModel.TYPE:
            return self.summary_configuration
        elif self.parameter.getType() == KeywordModel.TYPE:
            key_index_list = context_data.getKeyIndexList(self.parameter.getName())
            self.keyword_configuration.setKeyIndexList(key_index_list)
            return self.keyword_configuration
        elif self.parameter.getType() == FieldModel.TYPE:
            bounds = context_data.field_bounds
            self.field_configuration.setFieldBounds(*bounds)
            return self.field_configuration
        elif self.parameter.getType() == DataModel.TYPE:
            return None
        else:
            return None


class ConfigurationWidget(QWidget):
    """An abstract configuration widget."""
    def __init__(self):
        QWidget.__init__(self)
        self.layout = QFormLayout()
        self.layout.setRowWrapPolicy(QFormLayout.WrapLongRows)

        self.stateCombo = QComboBox()

        for state in enums.ert_state_enum.values():
           self.stateCombo.addItem(state.name)

        self.stateCombo.setCurrentIndex(0)

        self.layout.addRow("State:", self.stateCombo)

        self.setLayout(self.layout)

        self.connect(self.stateCombo, SIGNAL('currentIndexChanged(QString)'), self.applyConfiguration)

    def addRow(self, label, widget):
        self.layout.addRow(label, widget)

    def setParameter(self, parameter):
        self.parameter = parameter
        self.applyConfiguration(False)

    def getState(self):
        selectedName = str(self.stateCombo.currentText())
        return enums.ert_state_enum.resolveName(selectedName)

    def emitConfigurationChanged(self, emit=True):
        if emit:
            self.emit(SIGNAL('configurationChanged()'))

    def applyConfiguration(self, emit=True):
        """Override! Set the user_data of self.paramater and optionally: emitConfigurationChanged()"""
        pass


class SummaryConfigurationWidget(ConfigurationWidget):
    def __init__(self):
        ConfigurationWidget.__init__(self)


    def applyConfiguration(self, emit=True):
        user_data = {'state': self.getState()}
        self.parameter.setUserData(user_data)
        self.emitConfigurationChanged(emit)

        
class FieldConfigurationWidget(ConfigurationWidget):
    def __init__(self):
        ConfigurationWidget.__init__(self)

        self.keyIndexI = QSpinBox()
        self.keyIndexI.setMinimum(1)

        self.addRow("i:", self.keyIndexI)

        self.keyIndexJ = QSpinBox()
        self.keyIndexJ.setMinimum(1)
        self.addRow("j:", self.keyIndexJ)

        self.keyIndexK = QSpinBox()
        self.keyIndexK.setMinimum(1)
        self.addRow("k:", self.keyIndexK)

        self.setFieldBounds(1, 1, 1)

        self.connect(self.keyIndexI, SIGNAL('valueChanged(int)'), self.applyConfiguration)
        self.connect(self.keyIndexJ, SIGNAL('valueChanged(int)'), self.applyConfiguration)
        self.connect(self.keyIndexK, SIGNAL('valueChanged(int)'), self.applyConfiguration)

    def setFieldBounds(self, i, j, k):
        self.keyIndexI.setMaximum(i)
        self.keyIndexJ.setMaximum(j)
        self.keyIndexK.setMaximum(k)

    def getFieldPosition(self):
        return (self.keyIndexI.value(), self.keyIndexJ.value(), self.keyIndexK.value())

    def setParameter(self, parameter):
        self.parameter = parameter
        self.applyConfiguration(False)

    def applyConfiguration(self, emit=True):
        user_data = {'state': self.getState(), 'field_position': self.getFieldPosition()}
        self.parameter.setUserData(user_data)
        self.emitConfigurationChanged(emit)


class KeywordConfigurationWidget(ConfigurationWidget):
    def __init__(self):
        ConfigurationWidget.__init__(self)
        self.keyIndexCombo = QComboBox()
        self.addRow("Key index:", self.keyIndexCombo)

        self.connect(self.keyIndexCombo, SIGNAL('currentIndexChanged(QString)'), self.applyConfiguration)

    def setKeyIndexList(self, list):
        self.disconnect(self.keyIndexCombo, SIGNAL('currentIndexChanged(QString)'), self.applyConfiguration)
        self.keyIndexCombo.clear()
        self.keyIndexCombo.addItems(list)
        self.connect(self.keyIndexCombo, SIGNAL('currentIndexChanged(QString)'), self.applyConfiguration)

    def setParameter(self, parameter):
        self.parameter = parameter
        self.applyConfiguration(False)

    def applyConfiguration(self, emit=True):
        user_data = {'state': self.getState(), 'key_index' : self.getKeyIndex()}
        self.parameter.setUserData(user_data)
        self.emitConfigurationChanged(emit)

    def getKeyIndex(self):
        return str(self.keyIndexCombo.currentText())


