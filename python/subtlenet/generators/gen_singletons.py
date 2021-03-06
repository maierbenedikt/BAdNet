from _common import *

_truths = ['nprongs']
truths = {_truths[x]:x for x in xrange(len(_truths))}

def make_coll(fpath):
    coll = obj.GenCollection()
    coll.add_categories(['singletons'], fpath)
    return coll

def generate(collections, 
             variables=config.gen_default_variables,
             mus=config.gen_default_mus,
             sigmas=config.gen_default_sigmas,
             partition='train', 
             batch=32, 
             repartition=True,
             decorr_mass=False,
             decorr_pt=False,
             normalize=False):
    small_batch = max(1, int(batch / len(collections)))
    generators = {c:c.generator(components=['singletons', c.weight,'truth'],
                                partition=partition, 
                                batch=small_batch, 
                                repartition=repartition,
                                normalize=normalize) 
                    for c in collections}
    var_idx = [config.gen_singletons[x] for x in variables]
    mus = np.array(mus)
    sigmas = np.array(sigmas)
    msd_index = config.gen_singletons['msd']
    pt_index = config.gen_singletons['pt']
    msd_norm_factor = 1. / config.max_mass 
    pt_norm_factor = 1. / (config.max_pt - config.min_pt)
    def xform_mass(x):
        binned = (np.minimum(x, config.max_mass) * msd_norm_factor * (config.n_decorr_bins - 1)).astype(np.int)
        onehot = np_utils.to_categorical(binned, config.n_decorr_bins)
        return onehot
    def xform_pt(x):
        binned = (np.minimum(x-config.min_pt, config.max_pt-config.min_pt) 
                  * pt_norm_factor 
                  * (config.n_decorr_bins - 1)
                 ).astype(np.int)
        onehot = np_utils.to_categorical(binned, config.n_decorr_bins)
        return onehot
    while True: 
        inputs = []
        outputs = []
        weights = []
        for c in collections:
            data = {k:v.data for k,v in next(generators[c]).iteritems()}
            inputs.append([data['singletons'][:,var_idx]])
            # need to apply osme normalization to the inputs:
            inputs[-1][0] -= mus 
            inputs[-1][0] /= sigmas 
            
            nprongs = np_utils.to_categorical(
                    np.clip(
                        data['truth'][:,truths['nprongs']].astype(np.int), 
                        0, config.n_truth
                        ),
                    config.n_truth
                )
            o = [nprongs]
            w = [data[c.weight]]

            if decorr_mass:
                mass = xform_mass(data['singletons'][:,msd_index])
                o.append(mass)
                w.append(w[0] * nprongs[:,config.adversary_mask])

            if decorr_pt:
                pt = xform_pt(data['singletons'][:,pt_index])
                o.append(pt)
                w.append(w[0] * nprongs[:,config.adversary_mask])

            outputs.append(o)
            weights.append(w)

        merged_inputs = []
        for j in xrange(1):
            merged_inputs.append(np.concatenate([v[j] for v in inputs], axis=0))

        merged_outputs = []
        merged_weights = []
        NOUTPUTS = 1 + int(decorr_pt) + int(decorr_mass) 
        for j in xrange(NOUTPUTS):
            merged_outputs.append(np.concatenate([v[j] for v in outputs], axis=0))
            merged_weights.append(np.concatenate([v[j] for v in weights], axis=0))

        yield merged_inputs, merged_outputs, merged_weights

