from ecl.util import BoolVector

from res.enkf import ResConfig, ErtRunContext, EnKFMain, EnkfConfigNode, EnkfNode, NodeId
from res.server import SimulationContext
from .batch_simulator_context import BatchContext

class BatchSimulator(object):

    def __init__(self, res_config, controls, results):
        """Will create simulator which can be used to run multiple simulations.

        The @res_config argument should be a ResConfig object, representing the
        fully configured state of libres.


        The @controls argument configures which parameters the simulator should
        get when actually simulating. The @controls argument should be a
        dictionary like this:

            controls = {"cmode": ["Well","Group"], "order" : ["W1", "W2", "W3"]}

        In this example the simulator will expect two arrays 'cmode' and
        'order', consisting of two and three elements respectively. When
        actually simualating these values will be written to json files looking
        like:

             cmode.json = {"Well" : 1.0, "Group" : 2.0}
             order.json = {"W1" : 1, "W2" : 1.0, "W3": 1.0}

        When later invoking the start() method the simulator expects to get
        values for all parameters configured with the @controls argument,
        otherwise an exception will be raised. Internally in libres code the
        controls will be implemented as 'ext_param' instances.


        The @results argument is a list of keys of results which the simulator
        expects to be generated by the forward model. If argument @results
        looks like:

             results = ["CMODE", "order"]

        The simulator will look for the files 'CMODE_0' and 'order_0' in the
        simulation folder. If those files are not produced by the simulator an
        exception will be raised.
        """
        if not isinstance(res_config, ResConfig):
            raise ValueError("The first argument must be valid ResConfig instance")

        self.res_config = res_config
        self.ert = EnKFMain( self.res_config )
        self.control_keys = []
        self.result_keys = []

        ens_config = self.res_config.ensemble_config
        for key in controls.keys():
            ens_config.addNode( EnkfConfigNode.create_ext_param( key , controls[key] ))
            self.control_keys.append(key)

        for key in results:
            ens_config.addNode( EnkfConfigNode.create_gen_data( key , "{}_%d".format(key)))
            self.result_keys.append(key)




    def start(self, case_name, controls):
        """Will start batch simulation, returning a handle to query status and results.

        The start method will submit simulations to the queue system and then
        return a RobustContext handle which can be used to query for simulation
        status and results. The @case_name argument should just be string which
        will be used as name for the storage of these simulations in the
        system. The @controls argument is the set of control values, and the
        corresponding ID of the external realisation used for the simulations.
        The @control argument must match the control argument used when the
        simulator was instantiated. Assuming the following @control argument
        was passed to simulator construction:

             controls = {"cmode": ["Well","Group"], "order" : ["W1", "W2", "W3"]}

        Then the following @controls argument can be used in the start method
        to simulate four simulations:

              [ (1, {"cmode" : [1 ,2], "order" : [2,2,5]}),
                (1, {"cmode" : [1, 3], "order" : [2,2,7]}),
                (1, {"cmode" : [1, 7], "order" : [2,0,5]}),
                (2, {"cmode" : [1,-1], "order" : [2,2,1]})]

        The first integer argument in the tuple is the realisation id, so this
        simulation batch will consist of a total of four simulations, where the
        three first are based on realisation 1, and the last is based on
        realisation 2.

        Observe that only one BatchSimulator should actually be running at a
        time, so when you have called the 'start' method you need to let that
        batch complete before you start a new batch.
        """
        ens_config = self.res_config.ensemble_config
        fsm = self.ert.getEnkfFsManager( )
        fs = fsm.getFileSystem(case_name)

        for sim_id, (geo_id, control_dict)  in enumerate(controls):
            assert isinstance(geo_id, int)

            node_id = NodeId( 0, sim_id)
            if len(control_dict) != len(self.control_keys):
                raise ValueError("Not all keys supplied in controls")

            for key in control_dict.keys():
               config_node = ens_config[key]
               ext_config = config_node.getModelConfig( )
               values = control_dict[key]
               if not len(values) == len(ext_config):
                   raise ValueError("Wrong number of values for:%s" % key)

               node = EnkfNode(config_node)
               ext_node = node.as_ext_param( )
               ext_node.set_vector(values)
               node.save(fs, node_id)


        # The input should be validated before we instantiate the BatchContext
        # object, at that stage a job_queue object with multiple threads is
        # started, and things will typically be in a quite sorry state if an
        # exception occurs.
        itr = 0
        mask = BoolVector( default_value = True, initial_size = len(controls) )
        sim_context = BatchContext(self.result_keys, self.ert, fs, mask, itr)

        for sim_id, (geo_id, control_dict)  in enumerate(controls):
            sim_context.addSimulation(sim_id, geo_id)

        return sim_context
