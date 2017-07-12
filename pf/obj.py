import numpy as np 
from os.path import isfile 
from os import environ
environ['KERAS_BACKEND'] = 'tensorflow'
from glob import glob 
from keras.utils import np_utils

DEBUG = False 

_singletons = ['pt','eta','mass','msd','rho','tau32','tau21','flavour','nbHadrons','nProngs']
singletons = {_singletons[x]:x for x in xrange(len(_singletons))}

class DataObject(object):
    def __init__(self, fpaths):
        self.inputs = fpaths
        self.loaded = []
        self.n_available = 0 
        self.data = None 
    def load(self, idx=-1, memory=True):
        if len(self.loaded) == len(self.inputs):
            self.loaded = []
        if idx > 0:
            fpath = self.inputs[idx]
            if DEBUG: print 'Loading',fpath
            self.data = np.load(fpath)
            self.n_available = self.data.shape[0]
            if memory:
                self.loaded.append(fpath)
            return 
        else:
            for fpath in self.inputs:
                if fpath not in self.loaded:
                    if DEBUG: print 'Loading',fpath
                    self.data = np.load(fpath)
                    self.n_available = self.data.shape[0]
                    if memory:
                        self.loaded.append(fpath)
                    return 
    def __getitem__(self, indices=None):
        if indices:
            return self.data[indices]
        else:
            return self.data 


class DataCollection(object):
    def __init__(self):
        self.objects = {}
        self.input_partitions = None 
        self.cached_input_partitions = None 
    def add_classes(self, names, fpath):
        if DEBUG: print 'Searching for files...\r',
        self.objects[name] = DataObject(glob(fpath))
        if not len(self.objects[name].inputs):
            print 'ERROR: class %s has no inputs'%name
        if DEBUG: print 'Found files                 '
    def partition(self, train_frac=0.33, test_frac=0.33):
        n_inputs = None 
        self.input_partitions = {'train':[], 'test':[], 'validate':[]} 
        for _,v in self.objects.iteritems():
            if n_inputs:
                n_inputs = min(n_inputs, len(v.inputs))
            else:
                n_inputs = len(v.inputs)
        n_train = train_frac * n_inputs
        n_test = (train_frac + test_frac) * n_inputs
        shuffler = range(n_inputs)
        np.random.shuffle(shuffler)
        for idx in xrange(n_inputs):
            sidx = shuffler[idx]
            if idx > n_test:
                self.input_partitions['validate'].append(sidx)
            elif idx > n_train:
                self.input_partitions['test'].append(sidx)
            else:
                self.input_partitions['train'].append(sidx)
        self.cached_input_partitions = {}
        for k,v in self.input_partitions.iteritems():
            self.cached_input_partitions[k] = v[:]
    def load(self, idx=-1, partition=None):
        if partition:
            if not self.input_partitions:
                self.partition() 
            if not len(self.input_partitions[partition]):
                self.input_partitions[partition] = self.cached_input_partitions[partition][:]
            idx = self.input_partitions[partition].pop(0)
        for k,v in self.objects.iteritems():
            v.load(idx)
    def n_available(self):
        ns = [v.n_available for _,v in self.objects.iteritems()]
        assert(max([abs(x - ns[0]) for x in ns]) == 0)
        return ns[0]
    def __getitem__(self, indices=None):
        data = {}
        for k,v in self.objects.iteritems():
            data[k] = v[indices]
        return data 

class NH1(object):
    def __init__(self, bins):
        self.bins = bins 
        self._content = {x:0 for x in xrange(len(bins)+1)}
    def find_bin(self, x):
        for ix in xrange(len(self.bins)):
            if x < self.bins[ix]:
                return ix 
        return len(self.bins)
    def get_content(self, ix):
        return self._content[ix]
    def set_content(self, ix):
        self._content[ix] = 0
    def fill(self, x, y=1):
        self._content[self.find_bin(x)] += y
    def invert(self):
        for k,v in self._content.iteritems():
            if v:
                self._content[k] = 1./v 
    def eval_array(self, arr):
        ret = np.empty(arr.shape)
        for ix in xrange(arr.shape[0]):
            ret[ix] = self.get_content(self.find_bin(arr[ix]))
        return ret 

class PFSVCollection(DataCollection):
    def __init__(self):
        super(PFSVCollection, self).__init__()
        self.pt_weight = None 
    def add_classes(self, names, fpath):
        '''
        fpath must be of the form /some/path/to/files_*_XXXX.npy, 
        where XXXX gets replaced by the names
        '''
        basefiles = glob(fpath.replace('XXXX','singletons'))
        to_add = {n:[] for n in names}
        for f in basefiles:
            missing = False 
            for n in names:
                if not isfile(f.replace('singletons', n)):
                    missing = True 
                    break 
            if missing:
                continue 
            for n in names:
                to_add[n].append(f.replace('singletons', n))
        for n,fs in to_add.iteritems():
            self.objects[n] = DataObject(fs)
    def weight(self):
        if DEBUG: print 'Calculating weight...\r',
        n_total = 0 
        self.pt_weight = NH1(
            [0,40,80,120,160,200,250,300,350,400,450,500,600,700,800,1000,1200,1400,2000]
            )
        for o in self.objects['singletons'].inputs:
            pt = np.load(o)[:,singletons['pt']]
            for x in pt:
                self.pt_weight.fill(x)
        self.pt_weight.invert()
        if DEBUG: print 'Calculated weight         '
    def __getitem__(self, indices=None):
        data = super(PFSVCollection, self).__getitem__(indices)
        data['weight'] = self.pt_weight.eval_array(data['singletons'][:,singletons['pt']])
        data['nP'] = np_utils.to_categorical(data['singletons'][:,singletons['nProngs']].astype(np.int),5)
        data['nB'] = np_utils.to_categorical(data['singletons'][:,singletons['nbHadrons']].astype(np.int),5)
        return data 
    def generator(self, partition='train', batch=5):
        # used as a generator for training data
        self.weight()
        while True:
            self.load(partition=partition)
            data = self.__getitem__()
            inputs = [data[x] for x in ['charged', 'inclusive', 'sv']]
            outputs = [data[x] for x in ['nP', 'nB']]
            weights = data['weight']
            N = weights.shape[0]
            n_batches = int(N / batch + 1) 
            for ib in xrange(n_batches):
                lo = ib * batch 
                hi = min(N, (ib + 1) * batch)
                i = [x[lo:hi] for x in inputs]
                o = [x[lo:hi] for x in outputs]
                w = weights[lo:hi]
                yield i, o, w 

def generatePFSV(collections, partition='train', batch=32):
    small_batch = max(1, int(batch / len(collections)))
    generators = {c:c.generator(partition=partition, batch=small_batch) for c in collections}
    while True: 
        inputs = []
        outputs = []
        weights = []
        for c in collections:
            i, o, w = next(generators[c])
            inputs.append(i)
            outputs.append(o)
            weights.append(w)
        merged_inputs = []
        for j in xrange(3):
            merged_inputs.append(np.concatenate([v[j] for v in inputs], axis=0))
        merged_outputs = []
        for j in xrange(2):
            merged_outputs.append(np.concatenate([v[j] for v in outputs], axis=0))
        merged_weights = np.concatenate(weights, axis=0)
        yield merged_inputs, merged_outputs, [merged_weights, merged_weights]